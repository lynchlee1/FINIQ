# Ontology Graph System Documentation

The FINIQ Ontology Graph System extracts, structures, and queries complex relationships between corporate disclosures, issuance events, securities, fund usages, shareholder meetings, and investors (companies, organizations, and individuals). 

It is designed for high-performance interactive UI visualization, offering sub-millisecond query latency and automated clutter-reduction heuristics.

---

## 1. Overview & Data Schema

The ontology builds a rich semantic network containing the following nodes and edges:

### Nodes (Entities)
*   **Company**: Publicly traded or unlisted corporate entities.
*   **Person**: Individual investors, directors, or candidates.
*   **Organization**: Non-corporate entities such as investment associations (조합), pension funds, or asset managers.
*   **IssuanceEvent**: Decision events for rights issuance (유무상증자) or bond issuance (사채발행).
*   **ShareholderMeeting**: Regular or extraordinary shareholder meeting events.
*   **Security**: Financial instruments issued (e.g. Common Stock, 3rd CB, 4th BW).
*   **FundUsage**: Programmed allocation of funds (e.g. Facility Funds, Operating Funds).
*   **Agenda**: Meeting proposals discussed during shareholder meetings.

### Edges (Relationships)
*   `EXECUTED` (Company $\rightarrow$ IssuanceEvent): A company executing a corporate action.
*   `ISSUED` (IssuanceEvent $\rightarrow$ Security): An event issuing a specific security.
*   `FOR_PURPOSE` (IssuanceEvent $\rightarrow$ FundUsage): The purpose allocation of the fund raising.
*   `ACQUIRED` (Investor $\rightarrow$ Security): An investor acquiring/allocating a security.
*   `HELD` (Company $\rightarrow$ ShareholderMeeting): A company holding a meeting.
*   `INCLUDES` (ShareholderMeeting $\rightarrow$ Agenda): Meeting agendas.
*   `DIRECTOR_OF` (Person $\rightarrow$ Company): Nominated or elected corporate directors.

---

## 2. Professional UI-focused Optimization Features

To guarantee fluid rendering and avoid freezing browser layouts, the system incorporates the following advanced algorithms:

### A. Minor Investor Collapsing (Graph Pruning)
When a corporate event or security has a massive list of minor investors, rendering all nodes blocks the UI's physics simulation thread. 
*   **Heuristic**: If the count of minor investors exceeds `collapse_minor_threshold` (default: `10`), the query service automatically:
    1. Sorts investors descending by their investment weight.
    2. Retains the top **3 major investors** as individual nodes.
    3. Collapses all remaining minor investors into a single virtual node: `기타 소액투자자 X명` (Grouped Minor Investors).
    4. Aggregates their total investment weight into a single edge.
*   **UI Benefit**: Keeps active node counts between **30–80**, maintaining smooth **60 FPS** WebGL/Canvas drag and zoom interactions.

### B. Entity Resolution (Corporate Merging)
*   Corporate name suffixes like `(주)`, `주식회사`, `(유)` are stripped and normalized.
*   A global registry maps company names to stock codes. If a corporate investor is a known public company in the system, it automatically resolves to its main `company_{stock_code}` node, exposing corporate group ownerships.

### C. Homonym Disambiguation (Person Scoping)
*   Individuals (Person) are assigned composite IDs scoped to their target company: `person_{company_id}_{normalized_name}`.
*   This prevents false-positive global merges of individuals with identical names across unrelated companies, while correctly merging them across multiple events of the same issuer.

---

## 3. High-Performance Query Service

All queries are handled by `OntologyGraphQueryService` (`src/finiq/data/ontology_query.py`), featuring a sub-millisecond in-memory adjacency list index.

### A. Subgraph Neighborhood query (`get_neighborhood`)
Fetches the local ego-network up to depth $N$ around a company or investor:
```python
subgraph = query_service.get_neighborhood(
    company_id="022180", 
    depth=2, 
    collapse_minor_threshold=10,
    as_of_date="2026-04-30" # Optional temporal filter
)
```

### B. Temporal Filtering (`as_of_date`)
Filters out any edges or events that occurred after the target date, allowing the UI to show the historical network state at any selected slider position.

### C. Relationship Pathfinder (`find_connection_paths`)
Traces all possible paths between two entities (e.g., Investor A and Company B) to uncover hidden linkages:
```python
paths = query_service.find_connection_paths(source_id="person_005930_KIM", target_id="company_022180")
```

### D. Ultimate Control Chain (`get_control_chain`)
Traces corporate ownership backwards to list UBOs (Ultimate Beneficial Owners):
```python
chain = query_service.get_control_chain(company_id="005930")
```

---

## 4. REST API Endpoints

The API is exposed via FastAPI routers in `src/finiq/market_desk/web/routers/market_data.py`:

*   **GET `/api/ontology/network`**: Get localized subgraph.
    *   Parameters: `company_id` (string), `investor_name` (string), `depth` (int, default: 2), `collapse_minor_threshold` (int, default: 10), `as_of_date` (string, ISO format).
*   **GET `/api/ontology/paths`**: Get paths between two nodes.
    *   Parameters: `source_id` (string), `target_id` (string), `max_depth` (int, default: 5).
*   **GET `/api/ontology/control-chain`**: Trace control chain of a company.
    *   Parameters: `company_id` (string).

---

## 5. How to Run & Import

### A. Build the Ontology Graph JSON
To build the 250MB+ ontology graph from parsed KIND files:
```bash
./scripts/build_ontology.py --output tmp/ontology_graph.json
```

### B. Sync to live Neo4j Database
To synchronize the built ontology model directly to a Neo4j instance:
```bash
# Deploys constraint, tests APOC availability, and synchronizes in optimized batches
./scripts/sync_to_neo4j.py --input tmp/ontology_graph.json --uri bolt://localhost:7687 --username neo4j --password password
```

### C. Run Verification Tests
To run the full suite of unit and integration tests:
```bash
pytest tests/data/test_ontology_builder.py tests/data/test_sync_to_neo4j.py tests/market_desk/test_ontology_graph.py
```
