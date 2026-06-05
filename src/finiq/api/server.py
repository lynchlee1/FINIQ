from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from neo4j import GraphDatabase

app = FastAPI(title="FINIQ Ontology Graph API")

# Neo4j Driver (placeholder initialization, should be configured via environment)
# driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
driver = None

def get_driver():
    global driver
    if not driver:
        # For now, default to localhost. Can be configurable.
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "password"))
    return driver

class GraphNode(BaseModel):
    id: str
    label: str
    type: str
    group: Optional[str] = None
    tags: List[str] = []
    riskLevel: str = "low"
    riskDescription: str = ""
    properties: Dict[str, Any] = {}

class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str
    category: str = "other"
    weight: float = 0.0
    directed: bool = True
    properties: Dict[str, Any] = {}

class CypherQuery(BaseModel):
    query: str

@app.on_event("shutdown")
def shutdown_event():
    if driver:
        driver.close()

@app.get("/api/graph")
def fetch_graph():
    query = """
        MATCH (n:Entity)
        OPTIONAL MATCH (n)-[r]->(m:Entity)
        RETURN n, r, m
    """
    try:
        d = get_driver()
        with d.session() as session:
            result = session.run(query)
            nodes = {}
            edges = []
            for record in result:
                n = record.get("n")
                r = record.get("r")
                if n:
                    nid = n["id"]
                    if nid not in nodes:
                        nodes[nid] = {
                            "id": nid,
                            "label": n.get("label", nid),
                            "type": n.get("type", "Company"),
                            "group": n.get("group"),
                            "tags": n.get("tags", []),
                            "riskLevel": n.get("riskLevel", "low"),
                            "riskDescription": n.get("riskDescription", ""),
                            "properties": n.get("properties", {}) # might be stringified in neo4j, adjust if needed
                        }
                if r:
                    edges.append({
                        "id": r["id"],
                        "source": r["source"],
                        "target": r["target"],
                        "relation": r.get("relation", "related"),
                        "category": r.get("category", "other"),
                        "weight": r.get("weight", 0),
                        "directed": r.get("directed", True),
                        "properties": r.get("properties", {})
                    })
            return {"nodes": list(nodes.values()), "edges": edges}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/nodes")
def add_node(node: GraphNode):
    label_type = node.type.strip() or "Company"
    query = f"""
        MERGE (n:Entity {{id: $id}})
        SET n:Entity:{label_type}
        SET n.label = $label,
            n.type = $type,
            n.group = $group,
            n.tags = $tags,
            n.riskLevel = $riskLevel,
            n.riskDescription = $riskDescription,
            n.properties = $propertiesJson
    """
    try:
        d = get_driver()
        with d.session() as session:
            import json
            session.run(query, {
                "id": node.id,
                "label": node.label,
                "type": node.type,
                "group": node.group,
                "tags": node.tags,
                "riskLevel": node.riskLevel,
                "riskDescription": node.riskDescription,
                "propertiesJson": json.dumps(node.properties)
            })
        return {"status": "success", "message": f"Added node {node.id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/edges")
def add_edge(edge: GraphEdge):
    type_label = edge.relation.strip().upper().replace(" ", "_") or "RELATED_TO"
    query = f"""
        MATCH (a:Entity {{id: $source}})
        MATCH (b:Entity {{id: $target}})
        MERGE (a)-[r:{type_label} {{id: $id}}]->(b)
        SET r.relation = $relation,
            r.category = $category,
            r.weight = $weight,
            r.directed = $directed,
            r.source = $source,
            r.target = $target,
            r.properties = $propertiesJson
    """
    try:
        d = get_driver()
        with d.session() as session:
            import json
            session.run(query, {
                "id": edge.id,
                "source": edge.source,
                "target": edge.target,
                "relation": edge.relation,
                "category": edge.category,
                "weight": edge.weight,
                "directed": edge.directed,
                "propertiesJson": json.dumps(edge.properties)
            })
        return {"status": "success", "message": f"Added edge {edge.id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/nodes/{node_id}")
def delete_node(node_id: str):
    query = "MATCH (n:Entity {id: $id}) DETACH DELETE n"
    try:
        d = get_driver()
        with d.session() as session:
            session.run(query, {"id": node_id})
        return {"status": "success", "message": f"Deleted node {node_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/edges/{edge_id}")
def delete_edge(edge_id: str):
    query = "MATCH ()-[r {id: $id}]->() DELETE r"
    try:
        d = get_driver()
        with d.session() as session:
            session.run(query, {"id": edge_id})
        return {"status": "success", "message": f"Deleted edge {edge_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cypher")
def run_cypher(cypher: CypherQuery):
    try:
        d = get_driver()
        with d.session() as session:
            result = session.run(cypher.query)
            # A simplified response, real implementation would need to parse nodes and edges properly as in frontend
            # For brevity, returning generic records parsing logic
            nodes = {}
            edges = []
            for record in result:
                for key in record.keys():
                    val = record[key]
                    if not val:
                        continue
                    # Check if node or relationship
                    if hasattr(val, 'labels'):
                        nid = val.get("id") or str(val.element_id)
                        if nid not in nodes:
                            nodes[nid] = dict(val.items())
                    elif hasattr(val, 'type'):
                        rel = dict(val.items())
                        rel['relation'] = val.type
                        edges.append(rel)
            return {"nodes": list(nodes.values()), "edges": edges}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
