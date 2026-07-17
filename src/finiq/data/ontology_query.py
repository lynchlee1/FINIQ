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
                self.metadata = {}

        if self._initialized:
            return
        
        if not hasattr(self, "graph_json_path"):
            from finiq.config import PROJECT_ROOT
            self.graph_json_path = Path(graph_json_path or (PROJECT_ROOT / "resources" / "ontology_graph.json"))

        if not hasattr(self, "nodes_index"):
            self.nodes_index = {}
            self.edges_index = []
            self.adjacency = {}
            self.company_to_node_id = {}
            self.investor_to_node_id = {}
            self.metadata = {}
            self.is_loaded = False
            
        self._initialized = True

    def load_index(self, force: bool = False) -> bool:
        """Loads and indexes the ontology graph JSON file."""
        if self.is_loaded and not force:
            return True

        with open(self.graph_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        nodes_list = data.get("nodes", [])
        edges_list = data.get("edges", [])
        nodes_index = {node["id"]: node for node in nodes_list}
        dangling_edges = [
            edge
            for edge in edges_list
            if edge["source"] not in nodes_index or edge["target"] not in nodes_index
        ]
        if dangling_edges:
            edge_ids = ", ".join(str(edge.get("id") or "<missing id>") for edge in dangling_edges[:10])
            raise ValueError(f"Ontology graph edges reference missing nodes: {edge_ids}")
        adjacency = {node_id: [] for node_id in nodes_index}

        for edge in edges_list:
            src = edge["source"]
            tgt = edge["target"]
            if src in adjacency:
                adjacency[src].append(edge)
            if tgt in adjacency:
                adjacency[tgt].append(edge)

        company_to_node_id = {}
        investor_to_node_id = {}
        for node_id, node in nodes_index.items():
            node_type = node.get("type")
            props = node.get("properties", {})

            if node_type == "Company":
                code = props.get("stock_code")
                if code:
                    company_to_node_id[normalize_company_id(code)] = node_id
                    company_to_node_id[code] = node_id
                name = props.get("name") or node.get("label")
                if name:
                    company_to_node_id[name] = node_id
            elif node_type in ("Person", "Organization"):
                name = props.get("name") or node.get("label")
                if name:
                    investor_to_node_id.setdefault(name, []).append(node_id)

        self.metadata = data.get("metadata", {})
        self.nodes_index = nodes_index
        self.edges_index = edges_list
        self.adjacency = adjacency
        self.company_to_node_id = company_to_node_id
        self.investor_to_node_id = investor_to_node_id
        self.is_loaded = True
        return True

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

    def search_investors_disambiguation(self, query_name: str) -> List[Dict[str, Any]]:
        """Search for investors by name, returning detailed disambiguation context for homonyms."""
        self.load_index()
        norm_query = normalize_entity_name(query_name)
        if not norm_query:
            return []

        matching_nids = []

        # 1. Match in investor_to_node_id
        for name, nids in self.investor_to_node_id.items():
            if norm_query in normalize_entity_name(name):
                matching_nids.extend(nids)

        # 2. Match in company_to_node_id
        for name, nid in self.company_to_node_id.items():
            if norm_query in normalize_entity_name(name):
                if nid not in matching_nids:
                    matching_nids.append(nid)

        results = []
        for nid in set(matching_nids):
            node = self.nodes_index.get(nid)
            if not node:
                continue

            relations = []
            for edge in self.adjacency.get(nid, []):
                rel_type = edge["relation"]
                src = edge["source"]
                tgt = edge["target"]

                other_nid = tgt if src == nid else src
                other_node = self.nodes_index.get(other_nid, {})
                other_label = other_node.get("label", "")
                other_type = other_node.get("type", "")

                company_context = ""
                if other_nid.startswith("company_") and not other_nid.startswith("company_inv_"):
                    company_context = other_label
                elif rel_type == "ACQUIRED" and other_nid.startswith("security_"):
                    # Find ISSUED edge: IssuanceEvent -> Security
                    issuance_event_id = None
                    for e in self.adjacency.get(other_nid, []):
                        if e["relation"] == "ISSUED" and e["target"] == other_nid:
                            issuance_event_id = e["source"]
                            break
                    if issuance_event_id:
                        # Find EXECUTED edge: Company -> IssuanceEvent
                        for e in self.adjacency.get(issuance_event_id, []):
                            if e["relation"] == "EXECUTED" and e["target"] == issuance_event_id:
                                company_nid = e["source"]
                                company_context = self.nodes_index.get(company_nid, {}).get("label", "")
                                break
                elif other_nid.startswith("shareholder_meeting_"):
                    # Find HELD edge: Company -> ShareholderMeeting
                    for e in self.adjacency.get(other_nid, []):
                        if e["relation"] == "HELD" and e["target"] == other_nid:
                            company_nid = e["source"]
                            company_context = self.nodes_index.get(company_nid, {}).get("label", "")
                            break

                relations.append({
                    "relation": rel_type,
                    "target_type": other_type,
                    "target_label": other_label,
                    "company_context": company_context,
                    "date": edge.get("properties", {}).get("start_date") or edge.get("properties", {}).get("disclosed_date", "")
                })

            results.append({
                "id": nid,
                "label": node.get("label", ""),
                "type": node.get("type", ""),
                "properties": node.get("properties", {}),
                "connections": relations
            })

        return results
