#!/usr/bin/env python3
"""CLI script to build and export the ontology graph from parsed KIND disclosures."""

import argparse
import sys
from pathlib import Path

# Add src/ directory to python path if not already there
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from finiq.config import PROJECT_ROOT
from finiq.data.ontology_builder import build_ontology_graph, export_ontology_to_web_json


def main():
    parser = argparse.ArgumentParser(
        description="Build ontology graph from parsed KIND disclosures (rights issuance, bond issuance, shareholder meetings)."
    )
    parser.add_argument(
        "--rights-parsed",
        type=str,
        default=str(PROJECT_ROOT / "resources" / "KIND" / "rights_issuance" / "parsed-rights_issuance.json"),
        help="Path to parsed-rights_issuance.json",
    )
    parser.add_argument(
        "--rights-filtered",
        type=str,
        default=str(PROJECT_ROOT / "resources" / "KIND" / "rights_issuance" / "filtered.json"),
        help="Path to rights_issuance filtered.json",
    )
    parser.add_argument(
        "--bond-parsed",
        type=str,
        default=str(PROJECT_ROOT / "resources" / "KIND" / "bond_issuance" / "parsed-bond_issuance.json"),
        help="Path to parsed-bond_issuance.json",
    )
    parser.add_argument(
        "--bond-filtered",
        type=str,
        default=str(PROJECT_ROOT / "resources" / "KIND" / "bond_issuance" / "filtered.json"),
        help="Path to bond_issuance filtered.json",
    )
    parser.add_argument(
        "--sh-filtered",
        type=str,
        default=str(PROJECT_ROOT / "resources" / "KIND" / "shareholder_meeting" / "filtered.json"),
        help="Path to shareholder_meeting filtered.json",
    )
    parser.add_argument(
        "--sh-parsed",
        type=str,
        default=None,
        help="Path to parsed-shareholder_meeting.json (optional)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(PROJECT_ROOT / "resources" / "ontology_graph.json"),
        help="Output path for web-friendly ontology JSON",
    )

    args = parser.parse_args()

    print("Building ontology graph...")
    nodes, edges = build_ontology_graph(
        rights_issuance_path=args.rights_parsed,
        rights_filtered_path=args.rights_filtered,
        bond_issuance_path=args.bond_parsed,
        bond_filtered_path=args.bond_filtered,
        shareholder_meeting_filtered_path=args.sh_filtered,
        shareholder_meeting_parsed_path=args.sh_parsed,
    )

    print(f"Extraction summary:")
    print(f"  - Total unique nodes: {len(nodes)}")
    print(f"  - Total unique edges: {len(edges)}")

    if not nodes:
        print("Warning: No nodes were extracted. Please check if input files exist.")

    out_path = Path(args.output)
    print(f"Exporting to web-friendly format at: {out_path.resolve()}")
    export_ontology_to_web_json(nodes, edges, out_path)
    print("Ontology build complete.")


if __name__ == "__main__":
    main()
