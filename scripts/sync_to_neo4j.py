#!/usr/bin/env python3
"""Syncs the built ontology graph JSON file directly into the Neo4j database using optimized batch transactions."""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None

def main():
    if GraphDatabase is None:
        print("Error: 'neo4j' package is not installed. Please run 'pip install neo4j'.")
        sys.exit(1)
    parser = argparse.ArgumentParser(description="Sync ontology graph JSON file directly to Neo4j.")
    parser.add_argument(
        "--input",
        type=str,
        default="tmp/ontology_graph.json",
        help="Path to the web_ontology.json output file."
    )
    parser.add_argument(
        "--uri",
        type=str,
        default=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        help="Neo4j database connection URI."
    )
    parser.add_argument(
        "--username",
        type=str,
        default=os.getenv("NEO4J_USERNAME", "neo4j"),
        help="Neo4j username."
    )
    parser.add_argument(
        "--password",
        type=str,
        default=os.getenv("NEO4J_PASSWORD", "password"),
        help="Neo4j password."
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=2000,
        help="Batch size for inserts."
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear the Neo4j database before syncing."
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' does not exist. Build the ontology first using 'scripts/build_ontology.py'.")
        sys.exit(1)
        
    print(f"Loading ontology graph from '{input_path}'...")
    with open(input_path, "r", encoding="utf-8") as f:
        graph_data = json.load(f)
        
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    print(f"Loaded {len(nodes)} nodes and {len(edges)} edges.")
    
    print(f"Connecting to Neo4j database at {args.uri}...")
    try:
        driver = GraphDatabase.driver(args.uri, auth=(args.username, args.password))
        # Test connection
        driver.verify_connectivity()
    except Exception as exc:
        print(f"Failed to connect to Neo4j: {exc}")
        sys.exit(1)
        
    start_time = time.time()
    
    try:
        with driver.session() as session:
            # 1. Setup uniqueness constraint
            print("Creating uniqueness constraint on :Entity(id)...")
            session.run("CREATE CONSTRAINT FOR (e:Entity) REQUIRE e.id IS UNIQUE IF NOT EXISTS")
            
            # 2. Optionally clear the database
            if args.clear:
                print("Clearing Neo4j database...")
                session.run("MATCH (n:Entity) DETACH DELETE n")
                
            # 3. Import Nodes in Batches
            print(f"Importing {len(nodes)} nodes in batches of {args.batch_size}...")
            node_query = """
            UNWIND $batch AS row
            MERGE (n:Entity {id: row.id})
            SET n.label = row.label,
                n.type = row.type,
                n.group = row.group,
                n.tags = row.tags,
                n.riskLevel = COALESCE(row.riskLevel, 'low'),
                n.riskDescription = COALESCE(row.riskDescription, '')
            WITH n, row
            // Set dynamic properties
            UNWIND keys(row.properties) AS prop_key
            CALL apoc.create.setProperty(n, prop_key, row.properties[prop_key]) YIELD node
            RETURN count(*)
            """
            
            # Fallback query if APOC is not installed
            node_query_simple = """
            UNWIND $batch AS row
            MERGE (n:Entity {id: row.id})
            SET n.label = row.label,
                n.type = row.type,
                n.group = row.group,
                n.tags = row.tags,
                n.riskLevel = COALESCE(row.riskLevel, 'low'),
                n.riskDescription = COALESCE(row.riskDescription, '')
            // Set nested properties keys as flat values
            SET n += row.properties
            """
            
            # Check APOC presence
            has_apoc = False
            try:
                res = session.run("RETURN apoc.version() AS ver")
                if res.single():
                    has_apoc = True
                    print("APOC library detected, using advanced properties merge.")
            except Exception:
                pass
                
            active_node_query = node_query if has_apoc else node_query_simple
            
            for i in range(0, len(nodes), args.batch_size):
                batch = nodes[i : i + args.batch_size]
                session.run(active_node_query, batch=batch)
                print(f"  Nodes: {min(i + args.batch_size, len(nodes))}/{len(nodes)} synced...")
                
            # 4. Import Edges in Batches
            print(f"Importing {len(edges)} edges in batches of {args.batch_size}...")
            
            # Neo4j Cypher does not support dynamic relationship types in MERGE statement natively without APOC.
            # So if APOC is present, we use it, otherwise we fall back to generic relationship with properties.
            edge_query_apoc = """
            UNWIND $batch AS row
            MATCH (source:Entity {id: row.source})
            MATCH (target:Entity {id: row.target})
            CALL apoc.merge.relationship(source, row.relation, {id: row.id}, {}, target, {}) YIELD rel
            SET rel.category = row.category,
                rel.weight = row.weight,
                rel.directed = row.directed
            SET rel += row.properties
            """
            
            edge_query_simple = """
            UNWIND $batch AS row
            MATCH (source:Entity {id: row.source})
            MATCH (target:Entity {id: row.target})
            MERGE (source)-[rel:CONNECTED_TO {id: row.id}]->(target)
            SET rel.relation = row.relation,
                rel.category = row.category,
                rel.weight = row.weight,
                rel.directed = row.directed
            SET rel += row.properties
            """
            
            active_edge_query = edge_query_apoc if has_apoc else edge_query_simple
            if not has_apoc:
                print("APOC library not detected, using fallback CONNECTED_TO relationship with properties.")
                
            for i in range(0, len(edges), args.batch_size):
                batch = edges[i : i + args.batch_size]
                session.run(active_edge_query, batch=batch)
                print(f"  Edges: {min(i + args.batch_size, len(edges))}/{len(edges)} synced...")
                
        elapsed = time.time() - start_time
        print(f"\nOntology successfully synced to Neo4j in {elapsed:.2f} seconds!")
        
    finally:
        driver.close()

if __name__ == "__main__":
    main()
