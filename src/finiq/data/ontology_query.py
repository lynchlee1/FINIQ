"""Query and subgraph extraction services for the ontology graph."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from finiq.data.graph_models import EdgeTypes
from finiq.data.ontology_builder import (
    normalize_company_id,
    normalize_entity_name,
    parse_date_safe,
)


class OntologyGraphQueryService:
    """Provides fast query and subgraph extraction services for the ontology graph."""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, graph_json_path: str | Path | None = None):
        if graph_json_path is not None:
            new_path = Path(graph_json_path)
            if not hasattr(self, "graph_json_path") or self.graph_json_path != new_path:
                self.graph_json_path = new_path
                self.is_loaded = False
                self.nodes_index = {}
                self.edges_index = []
                self.adjacency = {}
                self.company_to_node_id = {}
                self.investor_to_node_id = {}

        if self._initialized:
            return
        
        if not hasattr(self, "graph_json_path"):
            from finiq.config import PROJECT_ROOT
            self.graph_json_path = Path(graph_json_path or (PROJECT_ROOT / "resources" / "ontology_graph.json"))
            # Fallback to tmp if resources version doesn't exist
            if not self.graph_json_path.exists():
                fallback = PROJECT_ROOT / "tmp" / "ontology_graph.json"
                if fallback.exists():
                    self.graph_json_path = fallback

        if not hasattr(self, "nodes_index"):
            self.nodes_index = {}
            self.edges_index = []
            self.adjacency = {}
            self.company_to_node_id = {}
            self.investor_to_node_id = {}
            self.is_loaded = False
            
        self._initialized = True

    def load_index(self, force: bool = False) -> bool:
        """Loads and indexes the ontology graph JSON file."""
        if self.is_loaded and not force:
            return True

        if not self.graph_json_path.exists():
            return False

        try:
            with open(self.graph_json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            nodes_list = data.get("nodes", [])
            edges_list = data.get("edges", [])
            
            self.nodes_index = {node["id"]: node for node in nodes_list}
            self.edges_index = edges_list
            
            # Build adjacency list
            self.adjacency = {}
            for node_id in self.nodes_index:
                self.adjacency[node_id] = []
                
            for edge in edges_list:
                src = edge["source"]
                tgt = edge["target"]
                
                # Check for references
                if src in self.adjacency:
                    self.adjacency[src].append(edge)
                if tgt in self.adjacency:
                    self.adjacency[tgt].append(edge)

            # Build company/investor lookup indices
            self.company_to_node_id = {}
            self.investor_to_node_id = {}
            for node_id, node in self.nodes_index.items():
                node_type = node.get("type")
                props = node.get("properties", {})
                
                if node_type == "Company":
                    code = props.get("stock_code")
                    if code:
                        self.company_to_node_id[normalize_company_id(code)] = node_id
                        self.company_to_node_id[code] = node_id
                    name = props.get("name") or node.get("label")
                    if name:
                        self.company_to_node_id[name] = node_id
                elif node_type in ("Person", "Organization"):
                    name = props.get("name") or node.get("label")
                    if name:
                        if name not in self.investor_to_node_id:
                            self.investor_to_node_id[name] = []
                        self.investor_to_node_id[name].append(node_id)

            self.is_loaded = True
            return True
        except Exception:
            return False

    def get_neighborhood(
        self, 
        company_id: str | None = None, 
        investor_name: str | None = None, 
        depth: int = 2,
        collapse_minor_threshold: int | None = 10,
        as_of_date: date | str | None = None,
    ) -> Dict[str, Any]:
        """Extract a subgraph (neighborhood) around a starting company or investor node, with optional temporal filtering."""
        self.load_index()
        
        target_date = None
        if as_of_date:
            target_date = parse_date_safe(str(as_of_date))

        start_nodes = []
        if company_id:
            normalized_code = normalize_company_id(company_id)
            node_id = self.company_to_node_id.get(normalized_code) or self.company_to_node_id.get(company_id)
            if node_id:
                start_nodes.append(node_id)
        
        if investor_name:
            nids = self.investor_to_node_id.get(investor_name)
            if nids:
                start_nodes.extend(nids)
            else:
                node_id = self.company_to_node_id.get(investor_name)
                if node_id:
                    start_nodes.append(node_id)

        if not start_nodes:
            return {"nodes": [], "edges": []}

        visited_nodes: Set[str] = set(start_nodes)
        visited_edges: Set[str] = set()
        
        # Traverse BFS style up to depth
        queue = [(node_id, 0) for node_id in start_nodes]
        head = 0
        while head < len(queue):
            current_id, current_depth = queue[head]
            head += 1
            
            if current_depth >= depth:
                continue
                
            neighbors = self.adjacency.get(current_id, [])
            for edge in neighbors:
                # Temporal filtering on edge start_date
                if target_date:
                    edge_start_raw = edge.get("properties", {}).get("start_date")
                    if edge_start_raw:
                        edge_start = parse_date_safe(edge_start_raw)
                        if edge_start > target_date:
                            continue

                src = edge["source"]
                tgt = edge["target"]
                edge_id = edge["id"]
                
                # Identify neighbor node
                neighbor_id = tgt if src == current_id else src
                
                if neighbor_id not in visited_nodes:
                    visited_nodes.add(neighbor_id)
                    queue.append((neighbor_id, current_depth + 1))
                    
                visited_edges.add(edge_id)

        # Collect node and edge objects
        nodes = [self.nodes_index[nid] for nid in visited_nodes if nid in self.nodes_index]
        edges_dict = {edge["id"]: edge for edge in self.edges_index}
        edges = [edges_dict[eid] for eid in visited_edges if eid in edges_dict]

        # Collapsing minor investors to prevent layout clutter and speed up rendering
        if collapse_minor_threshold is not None and collapse_minor_threshold > 0:
            target_to_acquired_edges = {}
            for edge in edges:
                if edge["relation"] == EdgeTypes.ACQUIRED:
                    tgt = edge["target"]
                    if tgt not in target_to_acquired_edges:
                        target_to_acquired_edges[tgt] = []
                    target_to_acquired_edges[tgt].append(edge)

            nodes_to_remove = set()
            edges_to_remove = set()
            new_nodes = []
            new_edges = []

            for tgt, group in target_to_acquired_edges.items():
                if len(group) > collapse_minor_threshold:
                    group.sort(key=lambda x: x.get("weight") or 0.0, reverse=True)
                    # Keep top 3, collapse indices 3 onwards
                    keep_count = min(3, len(group))
                    minor_group = group[keep_count:]
                    
                    if minor_group:
                        minor_count = len(minor_group)
                        total_weight = sum(e.get("weight") or 0.0 for e in minor_group)
                        
                        collapsed_node_id = f"collapsed_investors_{tgt}"
                        collapsed_node = {
                            "id": collapsed_node_id,
                            "label": f"기타 소액투자자 {minor_count}명",
                            "type": "Organization",
                            "group": "Organization",
                            "tags": ["Organization", "Collapsed"],
                            "properties": {
                                "count": minor_count,
                                "total_weight": total_weight,
                                "is_collapsed": True
                            }
                        }
                        
                        collapsed_edge = {
                            "id": f"collapsed_edge_{tgt}",
                            "source": collapsed_node_id,
                            "target": tgt,
                            "relation": EdgeTypes.ACQUIRED,
                            "category": EdgeTypes.ACQUIRED,
                            "weight": total_weight,
                            "directed": True,
                            "properties": {
                                "is_collapsed": True,
                                "investor_count": minor_count
                            }
                        }
                        
                        new_nodes.append(collapsed_node)
                        new_edges.append(collapsed_edge)
                        
                        for e in minor_group:
                            edges_to_remove.add(e["id"])
                            nodes_to_remove.add(e["source"])

            kept_nodes = set()
            remaining_edges = []
            for e in edges:
                if e["id"] not in edges_to_remove:
                    remaining_edges.append(e)
                    kept_nodes.add(e["source"])
                    kept_nodes.add(e["target"])

            for e in new_edges:
                remaining_edges.append(e)
                kept_nodes.add(e["source"])
                kept_nodes.add(e["target"])

            remaining_nodes = []
            for n in nodes:
                if n["id"] not in nodes_to_remove or n["id"] in kept_nodes:
                    remaining_nodes.append(n)
            for vn in new_nodes:
                if vn["id"] in kept_nodes:
                    remaining_nodes.append(vn)
            
            nodes = remaining_nodes
            edges = remaining_edges

        return {"nodes": nodes, "edges": edges}

    def find_connection_paths(self, source_id: str, target_id: str, max_depth: int = 5) -> List[List[Dict[str, Any]]]:
        """Find all paths between source_id and target_id up to max_depth."""
        self.load_index()
        if source_id not in self.nodes_index or target_id not in self.nodes_index:
            return []

        results = []
        
        def dfs(curr_id: str, path: List[str], edges_path: List[Dict[str, Any]]):
            if curr_id == target_id:
                # Convert path to web format representations
                results.append({
                    "nodes": [self.nodes_index[nid] for nid in path],
                    "edges": list(edges_path)
                })
                return
            
            if len(path) > max_depth:
                return
                
            for edge in self.adjacency.get(curr_id, []):
                src = edge["source"]
                tgt = edge["target"]
                neighbor_id = tgt if src == curr_id else src
                
                if neighbor_id not in path:
                    dfs(neighbor_id, path + [neighbor_id], edges_path + [edge])

        dfs(source_id, [source_id], [])
        return results

    def get_control_chain(self, company_id: str) -> Dict[str, Any]:
        """Trace major corporate ownership chains backwards to find controlling entities."""
        self.load_index()
        normalized_code = normalize_company_id(company_id)
        node_id = self.company_to_node_id.get(normalized_code) or self.company_to_node_id.get(company_id)
        
        if not node_id:
            return {"nodes": [], "edges": []}

        visited_nodes = {node_id}
        visited_edges = set()
        
        # Traverse backward from Company node along EXECUTED, ISSUED, ACQUIRED relations
        # Company <- EXECUTED - Event <- ISSUED - Security <- ACQUIRED - Investor
        queue = [node_id]
        head = 0
        while head < len(queue):
            curr_id = queue[head]
            head += 1
            
            # Find any edge where curr_id is target or source
            for edge in self.adjacency.get(curr_id, []):
                relation = edge["relation"]
                src = edge["source"]
                tgt = edge["target"]
                
                # We want backward flow (Investor -> Security -> Event -> Company)
                should_traverse = False
                if src == curr_id:
                    if curr_id.startswith("company_") and relation == EdgeTypes.EXECUTED:
                        should_traverse = True
                    elif curr_id.startswith("issuance_event_") and relation == EdgeTypes.ISSUED:
                        should_traverse = True
                elif tgt == curr_id:
                    if curr_id.startswith("security_") and relation == EdgeTypes.ACQUIRED:
                        should_traverse = True

                if should_traverse:
                    neighbor_id = src if tgt == curr_id else tgt
                    if neighbor_id not in visited_nodes:
                        visited_nodes.add(neighbor_id)
                        queue.append(neighbor_id)
                    visited_edges.add(edge["id"])

        nodes = [self.nodes_index[nid] for nid in visited_nodes if nid in self.nodes_index]
        edges_dict = {edge["id"]: edge for edge in self.edges_index}
        edges = [edges_dict[eid] for eid in visited_edges if eid in edges_dict]
        
        return {"nodes": nodes, "edges": edges}
