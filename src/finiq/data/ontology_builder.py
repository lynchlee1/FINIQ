"""Ontology builder to extract entities and relations from parsed disclosures."""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from finiq.data.graph_models import (
    Agenda,
    Company,
    EdgeTypes,
    FundUsage,
    GraphEdge,
    GraphNode,
    IssuanceEvent,
    Organization,
    Person,
    Security,
    ShareholderMeeting,
)

# Suffixes/Keywords to distinguish Organization/Company from Person
ORG_COMPANY_PATTERNS = [
    r"\(주\)",
    r"주식회사",
    r"홀딩스",
    r"파트너스",
    r"캐피탈",
    r"인베스트먼트",
    r"조합",
    r"펀드",
    r"협회",
    r"공사",
    r"은행",
    r"증권",
    r"생명",
    r"화재",
    r"신탁",
    r"보험",
    r"기금",
    r"유한회사",
    r"합자회사",
    r"외국인",
    r"기관",
    r"투자자",
    r"코리아",
    r"재단",
    r"사모",
    r"자산운용",
    r"종합금융",
    r"금융투자",
    r"새마을금고",
    r"협동조합",
    r"공제회",
]


def normalize_company_id(company_id: str | None) -> str:
    """Normalize a textual KIND company identifier without discarding letters."""
    if not company_id:
        return ""
    normalized = str(company_id).strip()
    return normalized.zfill(6) if normalized.isdigit() else normalized


def parse_date_safe(date_str: str | None) -> date:
    """Parse a supported ontology event date."""
    if not date_str:
        raise ValueError("Ontology event date is required")
    
    date_str = str(date_str).strip()
    if len(date_str) >= 10:
        try:
            return date.fromisoformat(date_str[:10])
        except ValueError:
            pass

    match = re.search(r"(\d{4})[년\-\./\s]+(\d{1,2})[월\-\./\s]+(\d{1,2})", date_str)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            pass

    raise ValueError(f"Invalid ontology event date: {date_str!r}")


def _load_json_object(path: str | Path, *, source_name: str) -> dict[str, Any]:
    source_path = Path(path)
    if not source_path.is_file():
        raise FileNotFoundError(f"{source_name} does not exist: {source_path}")
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Failed to read {source_name}: {source_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{source_name} must contain a JSON object: {source_path}")
    return payload


def classify_investor_type(name: str) -> str:
    """Classify investor as 'Company', 'Organization', or 'Person'."""
    name_clean = name.strip()
    if not name_clean:
        return "Organization"
        
    # Check if matches any corporate/organizational keywords
    for pattern in ORG_COMPANY_PATTERNS:
        if re.search(pattern, name_clean):
            # If it explicitly says 주식회사 or (주), classify as Company, otherwise Organization
            if "주식회사" in name_clean or "(주)" in name_clean or "회사" in name_clean:
                return "Company"
            return "Organization"
            
    # Fallback to Person if name is short (usually 2-4 chars for Korean names)
    if 2 <= len(name_clean) <= 4:
        return "Person"
        
    return "Organization"


def normalize_entity_name(name: str) -> str:
    """Normalize corporate names by stripping common suffixes/prefixes and whitespace."""
    if not name:
        return ""
    n = name.strip().upper()
    # Remove corporate patterns
    patterns = [
        r"\(주\)", r"㈜", r"주식회사",
        r"\(유\)", r"유한회사",
        r"\(합\)", r"합자회사",
        r"\(재\)", r"재단법인",
        r"\(사\)", r"사단법인",
        r"\(합자\)", r"\(유한\)"
    ]
    for p in patterns:
        n = re.sub(p, "", n)
    n = re.sub(r"\s+", "", n)
    return n


def make_relative_path(p: str | Path | None) -> str:
    """Normalize absolute paths to be relative to the PROJECT_ROOT."""
    if not p:
        return ""
    p_str = str(p).strip()
    from finiq.config import PROJECT_ROOT
    root_str = str(PROJECT_ROOT)
    if p_str.startswith(root_str):
        rel = p_str[len(root_str):]
        if rel.startswith("/") or rel.startswith("\\"):
            rel = rel[1:]
        return rel.replace("\\", "/")
    return p_str


def build_ontology_graph(
    rights_issuance_path: str | Path | None = None,
    rights_filtered_path: str | Path | None = None,
    bond_issuance_path: str | Path | None = None,
    bond_filtered_path: str | Path | None = None,
    shareholder_meeting_filtered_path: str | Path | None = None,
    shareholder_meeting_parsed_path: str | Path | None = None,
) -> Tuple[Dict[str, GraphNode], List[GraphEdge], Dict[str, Any]]:
    """Build ontology graph components (nodes and edges) from parsed files, returning nodes, edges, and metadata."""
    nodes: Dict[str, GraphNode] = {}
    edges: List[GraphEdge] = []

    # Map normalized names of all companies to their stock_code node ID
    # This enables Entity Resolution to merge corporate investors with company nodes!
    company_name_to_id: Dict[str, str] = {}
    
    def index_companies(
        f_path: str | Path | None,
        *,
        current_schema_only: bool = False,
    ) -> None:
        if not f_path:
            return
        data = _load_json_object(f_path, source_name="ontology filtered source")
        for disclosure in data.get("disclosures", []):
            raw_id = disclosure.get("company_id")
            if not current_schema_only and not raw_id:
                raw_id = disclosure.get("company_key")
            code = normalize_company_id(raw_id)
            name = disclosure.get("company_name")
            if not current_schema_only and not name:
                name = disclosure.get("submitter")
            if code and name:
                norm_name = normalize_entity_name(name)
                company_name_to_id[norm_name] = f"company_{code}"

    index_companies(rights_filtered_path)
    index_companies(bond_filtered_path)
    index_companies(shareholder_meeting_filtered_path, current_schema_only=True)

    # Compile Graph Manifest & Freshness Metadata
    metadata = {
        "built_at": datetime.now().isoformat(),
        "source_coverage": {
            "rights_issuance": {
                "parsed_path": make_relative_path(rights_issuance_path) if rights_issuance_path else None,
                "filtered_path": make_relative_path(rights_filtered_path) if rights_filtered_path else None,
                "processed_count": 0,
                "skipped_count": 0,
            },
            "bond_issuance": {
                "parsed_path": make_relative_path(bond_issuance_path) if bond_issuance_path else None,
                "filtered_path": make_relative_path(bond_filtered_path) if bond_filtered_path else None,
                "processed_count": 0,
                "skipped_count": 0,
            },
            "shareholder_meeting": {
                "parsed_path": make_relative_path(shareholder_meeting_parsed_path) if shareholder_meeting_parsed_path else None,
                "filtered_path": make_relative_path(shareholder_meeting_filtered_path) if shareholder_meeting_filtered_path else None,
                "processed_count": 0,
                "skipped_count": 0,
            }
        },
        "validation_summary": {
            "missing_company_ids": 0,
            "duplicate_nodes_resolved": 0,
        }
    }

    # 1. Process Rights Issuance (유무상증자)
    _process_rights_issuance(
        nodes, edges, rights_issuance_path, rights_filtered_path, company_name_to_id, metadata
    )

    # 2. Process Bond Issuance (채권발행)
    _process_bond_issuance(
        nodes, edges, bond_issuance_path, bond_filtered_path, company_name_to_id, metadata
    )

    # 3. Process Shareholder Meetings (주주총회)
    _process_shareholder_meetings(
        nodes,
        edges,
        shareholder_meeting_filtered_path,
        shareholder_meeting_parsed_path,
        company_name_to_id,
        metadata,
    )

    # Record total counts
    metadata["total_nodes"] = len(nodes)
    metadata["total_edges"] = len(edges)

    return nodes, edges, metadata


def _process_rights_issuance(
    nodes: Dict[str, GraphNode],
    edges: List[GraphEdge],
    parsed_path: str | Path | None,
    filtered_path: str | Path | None,
    company_name_to_id: Dict[str, str],
    metadata: Dict[str, Any],
) -> None:
    if parsed_path is None:
        return
    parsed_path = Path(parsed_path)
    parsed_data = _load_json_object(parsed_path, source_name="rights issuance parsed source")

    # Load filtered data for company metadata mapping
    filtered_map = {}
    if filtered_path:
        filtered_data = _load_json_object(filtered_path, source_name="rights issuance filtered source")
        for disc in filtered_data.get("disclosures", []):
            acpt = disc.get("acpt_no")
            if acpt:
                filtered_map[acpt] = disc
    records = parsed_data.get("records", [])

    for rec in records:
        acpt_no = rec.get("acpt_no")
        if not acpt_no:
            metadata["source_coverage"]["rights_issuance"]["skipped_count"] += 1
            continue

        # Get metadata
        meta = filtered_map.get(acpt_no, {})
        raw_company_id = meta.get("company_id") or meta.get("company_key")
        stock_code = normalize_company_id(raw_company_id)
        company_name = meta.get("company_name") or rec.get("\uae30\uc5c5\uba85(\ubc1c\ud589\uc0ac)") or meta.get("submitter") or "\uc54c\uc218\uc5c6\uc74c"

        if not stock_code:
            metadata["source_coverage"]["rights_issuance"]["skipped_count"] += 1
            metadata["validation_summary"]["missing_company_ids"] += 1
            continue

        metadata["source_coverage"]["rights_issuance"]["processed_count"] += 1

        company_node_id = f"company_{stock_code}"
        if company_node_id not in nodes:
            nodes[company_node_id] = Company(
                id=company_node_id,
                name=company_name,
                stock_code=stock_code,
                properties={
                    "market": meta.get("market", ""),
                    "submitter": meta.get("submitter", ""),
                }
            )
        else:
            metadata["validation_summary"]["duplicate_nodes_resolved"] += 1

        # Create Issuance Event
        event_date = parse_date_safe(meta.get("disclosed_date") or meta.get("disclosed_at") or rec.get("\ub0a9\uc785\uc77c"))
        event_id = f"issuance_event_{acpt_no}"
        issuance_type = rec.get("\uc99d\uc790\uc725\ud615") or "\uc720\uc0c1\uc99d\uc790"
        
        nodes[event_id] = IssuanceEvent(
            id=event_id,
            event_date=event_date,
            issuance_type=issuance_type,
            properties={
                "title": rec.get("title", ""),
                "\uc99d\uc790\ubc29\uc2dd": rec.get("\uc99d\uc790\ubc29\uc2dd", ""),
                "\ub0a9\uc785\uc77c": rec.get("\ub0a9\uc785\uc77c", ""),
                "\uc0c1\uc7a5\uc608\uc815\uc77c": rec.get("\uc0c1\uc7a5\uc608\uc815\uc77c", ""),
                "\uc2e0\uc8fc\uad8c\uad50\ubd80\uc608\uc815\uc77c": rec.get("\uc2e0\uc8fc\uad8c\uad50\ubd80\uc608\uc815\uc77c", ""),
                "acpt_no": acpt_no,
                "doc_no": rec.get("doc_no", ""),
            }
        )

        doc_title = rec.get("title") or meta.get("title") or "\uc720\uc0c1\uc99d\uc790\uacb0\uc815"
        disclosed_str = event_date.isoformat() if event_date else ""
        rel_src_file = make_relative_path(rec.get("source_file"))

        # Edge: Company -[EXECUTED]-> IssuanceEvent
        edges.append(
            GraphEdge(
                source_id=company_node_id,
                target_id=event_id,
                edge_type=EdgeTypes.EXECUTED,
                start_date=event_date,
                document_type="\uc720\uc0c1\uc99d\uc790\uacb0\uc815",
                source_url=rel_src_file,
                properties={
                    "evidence": {
                        "document_title": doc_title,
                        "acpt_no": acpt_no,
                        "disclosed_date": disclosed_str,
                        "source_file": rel_src_file,
                        "details": {
                            "\uc99d\uc790\ubc29\uc2dd": rec.get("\uc99d\uc790\ubc29\uc2dd", ""),
                            "\uc99d\uc790\uc720\ud615": issuance_type,
                        }
                    }
                }
            )
        )

        # Extract Securities issued
        security_prices = {sec_type: price for sec_type, price in rec.get("\ubc1c\ud589\uac00\uc561", [])}
        main_security_node_id = None

        for sec_type, count in rec.get("\uc2e0\uc8fc\uc758 \uc885\ub958\uc640 \uc218", []):
            if not count or count <= 0:
                continue
            
            sec_id = f"security_{acpt_no}_{sec_type}"
            price = security_prices.get(sec_type, 0)
            
            if sec_id not in nodes:
                nodes[sec_id] = Security(
                    id=sec_id,
                    security_type=sec_type,
                    amount=count,
                    properties={
                        "price": price,
                        "currency": "KRW",
                        "total_value": count * price if price else None,
                    }
                )
            else:
                metadata["validation_summary"]["duplicate_nodes_resolved"] += 1

            if not main_security_node_id:
                main_security_node_id = sec_id

            # Edge: IssuanceEvent -[ISSUED]-> Security
            edges.append(
                GraphEdge(
                    source_id=event_id,
                    target_id=sec_id,
                    edge_type=EdgeTypes.ISSUED,
                    start_date=event_date,
                    weight=float(count),
                    properties={
                        "evidence": {
                            "document_title": doc_title,
                            "acpt_no": acpt_no,
                            "disclosed_date": disclosed_str,
                            "source_file": rel_src_file,
                            "details": {
                                "\uc2e0\uc8fc\uc758\uc885\ub958": sec_type,
                                "\ubc1c\ud589\uc8fc\uc2dd\uc218": count,
                                "\uc2e0\uc8fc\ubc1c\ud589\uac00\uc561": price
                            }
                        }
                    }
                )
            )

        # Extract Fund Usages
        for usage_type, amount in rec.get("\ubc1c\ud589\ubaa9\uc801", []):
            if not amount or amount <= 0:
                continue
            
            usage_id = f"fund_usage_{acpt_no}_{usage_type}"
            if usage_id not in nodes:
                nodes[usage_id] = FundUsage(
                    id=usage_id,
                    usage_type=usage_type,
                    planned_amount=float(amount),
                    properties={
                        "currency": "KRW"
                    }
                )
            else:
                metadata["validation_summary"]["duplicate_nodes_resolved"] += 1

            # Edge: IssuanceEvent -[FOR_PURPOSE]-> FundUsage
            edges.append(
                GraphEdge(
                    source_id=event_id,
                    target_id=usage_id,
                    edge_type=EdgeTypes.FOR_PURPOSE,
                    start_date=event_date,
                    weight=float(amount),
                    properties={
                        "evidence": {
                            "document_title": doc_title,
                            "acpt_no": acpt_no,
                            "disclosed_date": disclosed_str,
                            "source_file": rel_src_file,
                            "details": {
                                "\uc790\uae08\uc870\ub2ec\ubaa9\uc801": usage_type,
                                "\ubc30\uc815\uae08\uc561": float(amount)
                            }
                        }
                    }
                )
            )

        # Extract Investors
        for target_name, target_shares in rec.get("\ubc1c\ud589\ub300\uc0c1\uc790", []):
            target_name = target_name.strip()
            if not target_name or target_name == "-":
                continue
            
            shares = int(target_shares) if target_shares else 0
            inv_type = classify_investor_type(target_name)
            norm_name = normalize_entity_name(target_name)

            # Entity Resolution
            if norm_name in company_name_to_id:
                investor_id = company_name_to_id[norm_name]
                if investor_id not in nodes:
                    nodes[investor_id] = Company(
                        id=investor_id,
                        name=target_name,
                        stock_code=investor_id.replace("company_", "")
                    )
                else:
                    metadata["validation_summary"]["duplicate_nodes_resolved"] += 1
            else:
                if inv_type == "Person":
                    # Disambiguation: Scope individual investors to prevent cross-company homonym pollution.
                    investor_id = f"person_{stock_code}_{norm_name}"
                    if investor_id not in nodes:
                        nodes[investor_id] = Person(
                            id=investor_id,
                            name=target_name,
                            properties={"normalized_name": norm_name, "scoped_company": stock_code}
                        )
                    else:
                        metadata["validation_summary"]["duplicate_nodes_resolved"] += 1
                elif inv_type == "Company":
                    investor_id = f"company_inv_{norm_name}"
                    if investor_id not in nodes:
                        nodes[investor_id] = Company(
                            id=investor_id,
                            name=target_name,
                            properties={"normalized_name": norm_name, "is_unlisted": True}
                        )
                    else:
                        metadata["validation_summary"]["duplicate_nodes_resolved"] += 1
                else:
                    investor_id = f"org_{norm_name}"
                    if investor_id not in nodes:
                        nodes[investor_id] = Organization(
                            id=investor_id,
                            name=target_name,
                            properties={"normalized_name": norm_name}
                        )
                    else:
                        metadata["validation_summary"]["duplicate_nodes_resolved"] += 1

            # Edge: Investor -[ACQUIRED]-> Security (prefer main security, or fallback to event_id)
            target_node_id = main_security_node_id or event_id
            edges.append(
                GraphEdge(
                    source_id=investor_id,
                    target_id=target_node_id,
                    edge_type=EdgeTypes.ACQUIRED,
                    start_date=event_date,
                    weight=float(shares),
                    document_type="\uc720\uc0c1\uc99d\uc790\uacb0\uc815",
                    properties={
                        "acpt_no": acpt_no,
                        "shares": shares,
                        "evidence": {
                            "document_title": doc_title,
                            "acpt_no": acpt_no,
                            "disclosed_date": disclosed_str,
                            "source_file": rel_src_file,
                            "details": {
                                "\ubc30\uc815\uc790\uba85": target_name,
                                "\ubc30\uc815\uc8fc\uc2dd\uc218": shares,
                                "\ud22c\uc790\uc720\ud615": inv_type
                            }
                        }
                    }
                )
            )


def _process_bond_issuance(
    nodes: Dict[str, GraphNode],
    edges: List[GraphEdge],
    parsed_path: str | Path | None,
    filtered_path: str | Path | None,
    company_name_to_id: Dict[str, str],
    metadata: Dict[str, Any],
) -> None:
    if parsed_path is None:
        return
    parsed_path = Path(parsed_path)
    parsed_data = _load_json_object(parsed_path, source_name="bond issuance parsed source")

    # Load filtered data for company metadata mapping
    filtered_map = {}
    if filtered_path:
        filtered_data = _load_json_object(filtered_path, source_name="bond issuance filtered source")
        for disc in filtered_data.get("disclosures", []):
            acpt = disc.get("acpt_no")
            if acpt:
                filtered_map[acpt] = disc
    records = parsed_data.get("records", [])

    for rec in records:
        acpt_no = rec.get("acpt_no")
        if not acpt_no:
            metadata["source_coverage"]["bond_issuance"]["skipped_count"] += 1
            continue

        meta = filtered_map.get(acpt_no, {})
        raw_company_id = meta.get("company_id") or meta.get("company_key")
        stock_code = normalize_company_id(raw_company_id)
        company_name = rec.get("\uae30\uc5c5\uba85(\ubc1c\ud589\uc0ac)") or meta.get("company_name") or meta.get("submitter") or "\uc54c\uc218\uc5c6\uc74c"

        if not stock_code:
            metadata["source_coverage"]["bond_issuance"]["skipped_count"] += 1
            metadata["validation_summary"]["missing_company_ids"] += 1
            continue

        metadata["source_coverage"]["bond_issuance"]["processed_count"] += 1

        company_node_id = f"company_{stock_code}"
        if company_node_id not in nodes:
            nodes[company_node_id] = Company(
                id=company_node_id,
                name=company_name,
                stock_code=stock_code,
                properties={
                    "market": meta.get("market", ""),
                    "submitter": meta.get("submitter", ""),
                }
            )
        else:
            metadata["validation_summary"]["duplicate_nodes_resolved"] += 1

        # Create Issuance Event
        event_date = parse_date_safe(meta.get("disclosed_date") or meta.get("disclosed_at") or rec.get("\ub0a9\uc785\uc77c"))
        event_id = f"issuance_event_{acpt_no}"
        bond_type = rec.get("\uc885\ub958") or "\uc0ac\ucc44"
        
        nodes[event_id] = IssuanceEvent(
            id=event_id,
            event_date=event_date,
            issuance_type=f"{bond_type}\ubc1c\ud589",
            properties={
                "title": rec.get("title", ""),
                "\ud68c\ucc28": rec.get("\ud68c\ucc28", ""),
                "\ubc1c\ud589\uae08\uc561": rec.get("\ubc1c\ud589\uae08\uc561", 0),
                "\ub0a9\uc785\uc77c": rec.get("\ub0a9\uc785\uc77c", ""),
                "\ub9cc\uae30\uc77c": rec.get("\ub9cc\uae30\uc77c", ""),
                "\ud589\uc0ac\uac00\uc561": rec.get("\ud589\uc0ac\uac00\uc561", 0),
                "\uc0ac\ucc44\ubc1c\ud589\ubc29\ubc95": rec.get("\uc0ac\ucc44\ubc1c\ud589\ubc29\ubc95", ""),
                "acpt_no": acpt_no,
            }
        )

        doc_title = rec.get("title") or meta.get("title") or "\uc0ac\ucc44\ubc1c\ud589\uacb0\uc815"
        disclosed_str = event_date.isoformat() if event_date else ""
        rel_src_file = make_relative_path(rec.get("source_file"))

        # Edge: Company -[EXECUTED]-> IssuanceEvent
        edges.append(
            GraphEdge(
                source_id=company_node_id,
                target_id=event_id,
                edge_type=EdgeTypes.EXECUTED,
                start_date=event_date,
                document_type="\uc0ac\ucc44\ubc1c\ud589\uacb0\uc815",
                source_url=rel_src_file,
                properties={
                    "evidence": {
                        "document_title": doc_title,
                        "acpt_no": acpt_no,
                        "disclosed_date": disclosed_str,
                        "source_file": rel_src_file,
                        "details": {
                            "\uc0ac\ucc44\uc885\ub958": bond_type,
                            "\ud68c\ucc28": rec.get("\ud68c\ucc28", ""),
                            "\ubc1c\ud589\uae08\uc561": rec.get("\ubc1c\ud589\uae08\uc561", 0),
                        }
                    }
                }
            )
        )

        # Create Security node
        sec_id = f"security_{acpt_no}"
        sec_type = f"\uc81c{rec.get('\ud68c\ucc28', '') or '0'}\ud68c\ucc28 {bond_type}"
        amount = rec.get("\ubc1c\ud589\uae08\uc561")
        
        if sec_id not in nodes:
            nodes[sec_id] = Security(
                id=sec_id,
                security_type=sec_type,
                amount=int(amount) if amount else None,
                properties={
                    "\ub9cc\uae30\uc77c": rec.get("\ub9cc\uae30\uc77c", ""),
                    "\ud589\uc0ac\uac00\uc561": rec.get("\ud589\uc0ac\uac00\uc561", 0),
                }
            )
        else:
            metadata["validation_summary"]["duplicate_nodes_resolved"] += 1

        # Edge: IssuanceEvent -[ISSUED]-> Security
        edges.append(
            GraphEdge(
                source_id=event_id,
                target_id=sec_id,
                edge_type=EdgeTypes.ISSUED,
                start_date=event_date,
                weight=float(amount) if amount else None,
                properties={
                    "evidence": {
                        "document_title": doc_title,
                        "acpt_no": acpt_no,
                        "disclosed_date": disclosed_str,
                        "source_file": rel_src_file,
                        "details": {
                            "\uc0ac\ucc44\uc885\ub958": bond_type,
                            "\ud68c\ucc28": rec.get("\ud68c\ucc28", ""),
                            "\ubc1c\ud589\uae08\uc561": float(amount) if amount else 0.0
                        }
                    }
                }
            )
        )

        # Extract Fund Usages
        for usage_type, usage_amount in rec.get("\ubc1c\ud589\ubaa9\uc801", []):
            if not usage_amount or usage_amount <= 0:
                continue
            
            usage_id = f"fund_usage_{acpt_no}_{usage_type}"
            if usage_id not in nodes:
                nodes[usage_id] = FundUsage(
                    id=usage_id,
                    usage_type=usage_type,
                    planned_amount=float(usage_amount),
                )
            else:
                metadata["validation_summary"]["duplicate_nodes_resolved"] += 1

            # Edge: IssuanceEvent -[FOR_PURPOSE]-> FundUsage
            edges.append(
                GraphEdge(
                    source_id=event_id,
                    target_id=usage_id,
                    edge_type=EdgeTypes.FOR_PURPOSE,
                    start_date=event_date,
                    weight=float(usage_amount),
                    properties={
                        "evidence": {
                            "document_title": doc_title,
                            "acpt_no": acpt_no,
                            "disclosed_date": disclosed_str,
                            "source_file": rel_src_file,
                            "details": {
                                "\uc790\uae08\uc870\ub2ec\ubaa9\uc801": usage_type,
                                "\ubc30\uc815\uae08\uc561": float(usage_amount)
                            }
                        }
                    }
                )
            )

        # Extract Investors
        for target_name, target_amount in rec.get("\ud22c\uc790\uc790", []):
            target_name = target_name.strip()
            if not target_name or target_name == "-":
                continue
            
            amount_val = float(target_amount) if target_amount else 0.0
            inv_type = classify_investor_type(target_name)
            norm_name = normalize_entity_name(target_name)

            # Entity Resolution
            if norm_name in company_name_to_id:
                investor_id = company_name_to_id[norm_name]
                if investor_id not in nodes:
                    nodes[investor_id] = Company(
                        id=investor_id,
                        name=target_name,
                        stock_code=investor_id.replace("company_", "")
                    )
                else:
                    metadata["validation_summary"]["duplicate_nodes_resolved"] += 1
            else:
                if inv_type == "Person":
                    # Disambiguation: Scope individual investors to prevent cross-company homonym pollution.
                    investor_id = f"person_{stock_code}_{norm_name}"
                    if investor_id not in nodes:
                        nodes[investor_id] = Person(
                            id=investor_id,
                            name=target_name,
                            properties={"normalized_name": norm_name, "scoped_company": stock_code}
                        )
                    else:
                        metadata["validation_summary"]["duplicate_nodes_resolved"] += 1
                elif inv_type == "Company":
                    investor_id = f"company_inv_{norm_name}"
                    if investor_id not in nodes:
                        nodes[investor_id] = Company(
                            id=investor_id,
                            name=target_name,
                            properties={"normalized_name": norm_name, "is_unlisted": True}
                        )
                    else:
                        metadata["validation_summary"]["duplicate_nodes_resolved"] += 1
                else:
                    investor_id = f"org_{norm_name}"
                    if investor_id not in nodes:
                        nodes[investor_id] = Organization(
                            id=investor_id,
                            name=target_name,
                            properties={"normalized_name": norm_name}
                        )
                    else:
                        metadata["validation_summary"]["duplicate_nodes_resolved"] += 1

            # Edge: Investor -[ACQUIRED]-> Security
            edges.append(
                GraphEdge(
                    source_id=investor_id,
                    target_id=sec_id,
                    edge_type=EdgeTypes.ACQUIRED,
                    start_date=event_date,
                    weight=amount_val,
                    document_type="\uc0ac\ucc44\ubc1c\ud589\uacb0\uc815",
                    properties={
                        "acpt_no": acpt_no,
                        "amount": amount_val,
                        "evidence": {
                            "document_title": doc_title,
                            "acpt_no": acpt_no,
                            "disclosed_date": disclosed_str,
                            "source_file": rel_src_file,
                            "details": {
                                "\ud22c\uc790\uc790\uba85": target_name,
                                "\ud22c\uc790\uae08\uc561": amount_val,
                                "\ud22c\uc790\uc720\ud615": inv_type
                            }
                        }
                    }
                )
            )


_SHAREHOLDER_RELATION_EDGE_TYPES = {
    "includes": EdgeTypes.INCLUDES,
    "candidate_for": EdgeTypes.CANDIDATE_FOR,
    "elected_as": EdgeTypes.ELECTED_AS,
    "removed_from": EdgeTypes.REMOVED_FROM,
    "resigned_from": EdgeTypes.RESIGNED_FROM,
    "subject_of": EdgeTypes.SUBJECT_OF,
    "proposed": EdgeTypes.PROPOSED,
    "serves_at": EdgeTypes.SERVES_AT,
    "option_granted_by": EdgeTypes.OPTION_GRANTED_BY,
    "external_auditor_of": EdgeTypes.EXTERNAL_AUDITOR_OF,
    "electronic_voting_manager_for": EdgeTypes.ELECTRONIC_VOTING_MANAGER_FOR,
    "electronic_voting_system_provider_for": EdgeTypes.ELECTRONIC_VOTING_SYSTEM_PROVIDER_FOR,
    "transferor_of": EdgeTypes.TRANSFEROR_OF,
    "transferee_of": EdgeTypes.TRANSFEREE_OF,
    "proposed_allottee_of": EdgeTypes.PROPOSED_ALLOTTEE_OF,
    "merger_target_of": EdgeTypes.MERGER_TARGET_OF,
    "acquisition_target_of": EdgeTypes.ACQUISITION_TARGET_OF,
    "divestment_target_of": EdgeTypes.DIVESTMENT_TARGET_OF,
    "shareholder_of": EdgeTypes.SHAREHOLDER_OF,
}

_SHAREHOLDER_RELATION_ENDPOINT_KINDS = {
    "includes": ({"meeting"}, {"agenda"}),
    "candidate_for": ({"person"}, {"company"}),
    "elected_as": ({"person"}, {"company"}),
    "removed_from": ({"person"}, {"company"}),
    "resigned_from": ({"person"}, {"company"}),
    "subject_of": ({"person", "organization"}, {"agenda"}),
    "proposed": ({"person", "organization"}, {"agenda"}),
    "serves_at": ({"person"}, {"organization", "company"}),
    "option_granted_by": ({"person"}, {"company"}),
    "external_auditor_of": ({"organization"}, {"company"}),
    "electronic_voting_manager_for": ({"organization"}, {"meeting"}),
    "electronic_voting_system_provider_for": ({"organization"}, {"meeting"}),
    "transferor_of": ({"person", "organization"}, {"company"}),
    "transferee_of": ({"person", "organization"}, {"company"}),
    "proposed_allottee_of": ({"person", "organization"}, {"company"}),
    "merger_target_of": ({"organization"}, {"company", "agenda"}),
    "acquisition_target_of": ({"organization"}, {"company", "agenda"}),
    "divestment_target_of": ({"organization"}, {"company", "agenda"}),
    "shareholder_of": ({"person", "organization"}, {"company"}),
}


def _has_shareholder_source_evidence(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    raw_text = value.get("raw_text")
    return isinstance(raw_text, str) and bool(raw_text.strip())


def _is_truthy_correction_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}
    return False


def _shareholder_disclosure_phase(parsed_rec: dict[str, Any]) -> str:
    phase = str(parsed_rec.get("disclosure_phase") or "").strip().lower()
    return phase if phase in {"notice", "result"} else ""


def _shareholder_person_id(stock_code: str, name: str, birth_month: str = "") -> str:
    normalized_name = normalize_entity_name(name)
    birth_key = re.sub(r"\D", "", str(birth_month))
    suffix = f"_{birth_key}" if birth_key else ""
    return f"person_{stock_code}_{normalized_name}{suffix}"


def _shareholder_evidence(
    *,
    document_title: str,
    acpt_no: str,
    disclosed_date: str,
    source_file: str,
    details: dict[str, Any],
    extraction: Any = None,
) -> dict[str, Any]:
    merged_details = dict(extraction) if isinstance(extraction, dict) else {}
    merged_details.update(details)
    evidence = {
        "document_title": document_title,
        "acpt_no": acpt_no,
        "disclosed_date": disclosed_date,
        "source_file": source_file,
        "details": merged_details,
    }
    return evidence


def _create_shareholder_entities(
    *,
    raw_entities: list[Any],
    nodes: Dict[str, GraphNode],
    stock_code: str,
    company_name_to_id: Dict[str, str],
    invalid_local_refs: set[str],
    metadata: Dict[str, Any] | None,
) -> tuple[dict[str, str], dict[str, str]]:
    entity_ref_to_node_id: dict[str, str] = {}
    entity_ref_to_kind: dict[str, str] = {}
    for raw_entity in raw_entities:
        if not isinstance(raw_entity, dict):
            continue
        entity_ref = str(raw_entity.get("entity_ref") or "").strip()
        entity_type = str(raw_entity.get("entity_type") or "").strip().lower()
        name = str(raw_entity.get("name") or "").strip()
        if (
            not entity_ref
            or entity_ref in invalid_local_refs
            or entity_type not in {"person", "organization"}
            or not name
        ):
            continue

        attributes = raw_entity.get("attributes")
        attributes = dict(attributes) if isinstance(attributes, dict) else {}
        mentions = raw_entity.get("mentions")
        if isinstance(mentions, list):
            attributes["mentions"] = mentions
        normalized_name = normalize_entity_name(name)

        if entity_type == "person":
            birth_month = str(attributes.get("birth_month") or "").strip()
            node_id = _shareholder_person_id(stock_code, name, birth_month)
            node_properties = {
                **attributes,
                "normalized_name": normalized_name,
                "scoped_company": stock_code,
            }
            if node_id not in nodes:
                nodes[node_id] = Person(id=node_id, name=name, properties=node_properties)
            elif metadata:
                metadata["validation_summary"]["duplicate_nodes_resolved"] += 1
        else:
            node_id = company_name_to_id.get(normalized_name, f"org_{normalized_name}")
            if node_id not in nodes:
                if node_id.startswith("company_"):
                    nodes[node_id] = Company(
                        id=node_id,
                        name=name,
                        stock_code=node_id.removeprefix("company_"),
                        properties={**attributes, "normalized_name": normalized_name},
                    )
                else:
                    nodes[node_id] = Organization(
                        id=node_id,
                        name=name,
                        properties={**attributes, "normalized_name": normalized_name},
                    )
            elif metadata:
                metadata["validation_summary"]["duplicate_nodes_resolved"] += 1

        entity_ref_to_node_id[entity_ref] = node_id
        entity_ref_to_kind[entity_ref] = entity_type
    return entity_ref_to_node_id, entity_ref_to_kind


def _process_shareholder_parsed_details(
    *,
    nodes: Dict[str, GraphNode],
    edges: List[GraphEdge],
    parsed_rec: dict[str, Any],
    company_name_to_id: Dict[str, str],
    company_node_id: str,
    stock_code: str,
    event_id: str,
    event_date: date,
    parsed_meeting_date: date | None,
    disclosure_phase: str,
    acpt_no: str,
    document_title: str,
    disclosed_date: str,
    source_file: str,
    metadata: Dict[str, Any] | None,
) -> None:
    agenda_records = parsed_rec.get("agenda_records")
    raw_entities = parsed_rec.get("entities")
    relationships = parsed_rec.get("relationships")
    if not all(
        isinstance(value, list)
        for value in (agenda_records, raw_entities, relationships)
    ):
        return

    local_ref_counts: dict[str, int] = {}
    for agenda_record in agenda_records:
        if not isinstance(agenda_record, dict):
            continue
        agenda_ref = str(agenda_record.get("agenda_ref") or "").strip()
        if agenda_ref:
            local_ref_counts[agenda_ref] = local_ref_counts.get(agenda_ref, 0) + 1
    for raw_entity in raw_entities:
        if not isinstance(raw_entity, dict):
            continue
        entity_ref = str(raw_entity.get("entity_ref") or "").strip()
        if entity_ref:
            local_ref_counts[entity_ref] = local_ref_counts.get(entity_ref, 0) + 1
    invalid_local_refs = {
        local_ref
        for local_ref, count in local_ref_counts.items()
        if count > 1 or local_ref.startswith("@")
    }

    agenda_ref_to_node_id: dict[str, str] = {}
    for idx, agenda_record in enumerate(agenda_records):
        if not isinstance(agenda_record, dict):
            continue
        agenda_title = str(agenda_record.get("title") or "").strip()
        if not agenda_title:
            continue
        agenda_id = f"agenda_{acpt_no}_{idx}"
        agenda_status = agenda_record.get("status")
        agenda_properties = {
            key: value
            for key, value in agenda_record.items()
            if key not in {"title", "status"}
        }
        agenda_properties["index"] = idx
        if agenda_id not in nodes:
            nodes[agenda_id] = Agenda(
                id=agenda_id,
                title=agenda_title,
                status=str(agenda_status) if agenda_status else None,
                properties=agenda_properties,
            )
        elif metadata:
            metadata["validation_summary"]["duplicate_nodes_resolved"] += 1

        agenda_ref = str(agenda_record.get("agenda_ref") or "").strip()
        if agenda_ref and agenda_ref not in invalid_local_refs:
            agenda_ref_to_node_id[agenda_ref] = agenda_id

    entity_ref_to_node_id, entity_ref_to_kind = _create_shareholder_entities(
        raw_entities=raw_entities,
        nodes=nodes,
        stock_code=stock_code,
        company_name_to_id=company_name_to_id,
        invalid_local_refs=invalid_local_refs,
        metadata=metadata,
    )
    local_refs = {
        **agenda_ref_to_node_id,
        **entity_ref_to_node_id,
        "@reporting_company": company_node_id,
        "@meeting": event_id,
    }
    local_ref_kinds = {
        **{agenda_ref: "agenda" for agenda_ref in agenda_ref_to_node_id},
        **entity_ref_to_kind,
        "@reporting_company": "company",
        "@meeting": "meeting",
    }
    for relationship in relationships:
        if not isinstance(relationship, dict):
            continue
        relationship_type = str(relationship.get("relationship_type") or "").strip().lower()
        edge_type = _SHAREHOLDER_RELATION_EDGE_TYPES.get(relationship_type)
        source_ref = str(relationship.get("source_ref") or "").strip()
        target_ref = str(relationship.get("target_ref") or "").strip()
        source_id = local_refs.get(source_ref)
        target_id = local_refs.get(target_ref)
        endpoint_kinds = _SHAREHOLDER_RELATION_ENDPOINT_KINDS.get(relationship_type)
        evidence = relationship.get("evidence")
        if (
            not edge_type
            or not source_id
            or not target_id
            or not endpoint_kinds
            or local_ref_kinds.get(source_ref) not in endpoint_kinds[0]
            or local_ref_kinds.get(target_ref) not in endpoint_kinds[1]
            or not _has_shareholder_source_evidence(evidence)
        ):
            continue

        attributes = relationship.get("attributes")
        attributes = dict(attributes) if isinstance(attributes, dict) else {}
        outcome = str(attributes.get("outcome") or "").strip()
        if relationship_type in {
            "elected_as",
            "removed_from",
            "resigned_from",
            "option_granted_by",
        }:
            if disclosure_phase != "result":
                continue
            if outcome != "passed":
                continue

        is_active = None
        if relationship_type == "elected_as":
            is_active = True
        elif relationship_type in {"removed_from", "resigned_from"}:
            is_active = False
        elif relationship_type == "serves_at" and isinstance(
            attributes.get("is_current"), bool
        ):
            is_active = attributes["is_current"]
        elif relationship_type == "external_auditor_of":
            state = str(attributes.get("state") or "").strip().lower()
            is_active = (
                True if state == "current" else False if state == "former" else None
            )
        elif relationship_type == "shareholder_of" and isinstance(
            attributes.get("is_current"), bool
        ):
            is_active = attributes["is_current"]

        has_unknown_start = relationship_type in {
            "serves_at",
            "external_auditor_of",
            "removed_from",
            "resigned_from",
            "transferor_of",
            "transferee_of",
            "proposed_allottee_of",
            "merger_target_of",
            "acquisition_target_of",
            "divestment_target_of",
            "shareholder_of",
        }
        if has_unknown_start:
            relationship_start_date = None
        elif relationship_type in {
            "electronic_voting_manager_for",
            "electronic_voting_system_provider_for",
        }:
            relationship_start_date = parsed_meeting_date
        else:
            relationship_start_date = event_date

        edges.append(
            GraphEdge(
                source_id=source_id,
                target_id=target_id,
                edge_type=edge_type,
                start_date=relationship_start_date,
                end_date=(
                    parsed_meeting_date
                    if relationship_type in {"removed_from", "resigned_from"}
                    else None
                ),
                is_active=is_active,
                document_type="주주총회공시",
                properties={
                    **attributes,
                    "acpt_no": acpt_no,
                    "disclosure_phase": disclosure_phase,
                    "evidence": _shareholder_evidence(
                        document_title=document_title,
                        acpt_no=acpt_no,
                        disclosed_date=disclosed_date,
                        source_file=source_file,
                        details={
                            "relationship_type": relationship_type,
                            "source_ref": relationship.get("source_ref"),
                            "target_ref": relationship.get("target_ref"),
                        },
                        extraction=evidence,
                    ),
                },
            )
        )


def _shareholder_edge_office_type(edge: GraphEdge) -> str:
    return str(edge.properties.get("office_type") or "").strip().lower()


def _reconcile_shareholder_terminations(
    nodes: Dict[str, GraphNode],
    edges: List[GraphEdge],
) -> None:
    termination_edges = sorted(
        (
            edge
            for edge in edges
            if edge.edge_type in {EdgeTypes.REMOVED_FROM, EdgeTypes.RESIGNED_FROM}
            and edge.end_date is not None
        ),
        key=lambda edge: edge.end_date,
    )
    for termination in termination_edges:
        termination_office = _shareholder_edge_office_type(termination)
        source_node = nodes.get(termination.source_id)
        if not termination_office or not isinstance(source_node, Person):
            continue
        for appointment in edges:
            if (
                appointment.edge_type != EdgeTypes.ELECTED_AS
                or appointment.source_id != termination.source_id
                or appointment.target_id != termination.target_id
                or appointment.is_active is not True
                or appointment.start_date is None
                or appointment.start_date >= termination.end_date
                or _shareholder_edge_office_type(appointment) != termination_office
            ):
                continue
            appointment.end_date = termination.end_date
            appointment.is_active = False


def _process_shareholder_meetings(
    nodes: Dict[str, GraphNode],
    edges: List[GraphEdge],
    filtered_path: str | Path | None,
    parsed_path: str | Path | None,
    company_name_to_id: Dict[str, str],
    metadata: Dict[str, Any] | None = None,
) -> None:
    if filtered_path is None:
        return
    filtered_path = Path(filtered_path)
    filtered_data = _load_json_object(filtered_path, source_name="shareholder meeting filtered source")

    # Load parsed data if provided
    parsed_map = {}
    if parsed_path:
        parsed_data = _load_json_object(parsed_path, source_name="shareholder meeting parsed source")
        for rec in parsed_data.get("records", []):
            acpt = rec.get("acpt_no")
            if acpt:
                parsed_map[acpt] = rec
    disclosures = filtered_data.get("disclosures", [])

    for disc in disclosures:
        acpt_no = disc.get("acpt_no")
        if not acpt_no:
            if metadata:
                metadata["source_coverage"]["shareholder_meeting"]["skipped_count"] += 1
            continue

        if _is_truthy_correction_flag(disc.get("has_later_correction")):
            if metadata:
                metadata["source_coverage"]["shareholder_meeting"]["skipped_count"] += 1
            continue

        raw_company_id = disc.get("company_id")
        stock_code = normalize_company_id(raw_company_id)
        company_name = str(disc.get("company_name") or "").strip()

        if not stock_code or not company_name:
            if metadata:
                metadata["source_coverage"]["shareholder_meeting"]["skipped_count"] += 1
                metadata["validation_summary"]["missing_company_ids"] += 1
            continue

        parsed_rec = parsed_map.get(acpt_no)
        if not isinstance(parsed_rec, dict):
            if metadata:
                metadata["source_coverage"]["shareholder_meeting"]["skipped_count"] += 1
            continue

        raw_disclosed_date = disc.get("disclosed_date")
        raw_meeting_date = parsed_rec.get("meeting_date")
        title = str(disc.get("title") or "").strip()
        if not raw_disclosed_date or not raw_meeting_date or not title:
            if metadata:
                metadata["source_coverage"]["shareholder_meeting"]["skipped_count"] += 1
            continue
        disclosed_date = parse_date_safe(raw_disclosed_date)
        parsed_meeting_date = parse_date_safe(raw_meeting_date)

        if metadata:
            metadata["source_coverage"]["shareholder_meeting"]["processed_count"] += 1

        company_node_id = f"company_{stock_code}"
        if company_node_id not in nodes:
            nodes[company_node_id] = Company(
                id=company_node_id,
                name=company_name,
                stock_code=stock_code,
                properties={
                    "market": disc.get("market", ""),
                    "submitter": disc.get("submitter", ""),
                }
            )
        else:
            if metadata:
                metadata["validation_summary"]["duplicate_nodes_resolved"] += 1

        event_date = parsed_meeting_date
        event_id = f"shareholder_meeting_{acpt_no}"

        meeting_type = "\uc815\uae30\uc8fc\uc8fc\ucd1d\ud68c" if "\uc815\uae30" in title else ("\uc784\uc2dc\uc8fc\uc8fc\ucd1d\ud68c" if "\uc784\uc2dc" in title else "\uc8fc\uc8fc\ucd1d\ud68c")
        disclosure_phase = _shareholder_disclosure_phase(parsed_rec)

        if event_id not in nodes:
            nodes[event_id] = ShareholderMeeting(
                id=event_id,
                event_date=event_date,
                meeting_type=meeting_type,
                properties={
                    "title": title,
                    "acpt_no": acpt_no,
                    "disclosure_phase": disclosure_phase,
                }
            )
        else:
            if metadata:
                metadata["validation_summary"]["duplicate_nodes_resolved"] += 1

        doc_title = title
        disclosed_str = disclosed_date.isoformat()
        rel_src_file = make_relative_path(disc.get("source_file"))

        # Edge: Company -[HELD]-> ShareholderMeeting
        edges.append(
            GraphEdge(
                source_id=company_node_id,
                target_id=event_id,
                edge_type=EdgeTypes.HELD,
                start_date=event_date,
                document_type="\uc8fc\uc8fc\ucd1d\ud68c\uacf5\uc2dc",
                properties={
                    "evidence": {
                        "document_title": doc_title,
                        "acpt_no": acpt_no,
                        "disclosed_date": disclosed_str,
                        "source_file": rel_src_file,
                        "details": {
                            "\ud68c\uc758\uc885\ub958": meeting_type
                        }
                    }
                }
            )
        )

        if parsed_rec:
            _process_shareholder_parsed_details(
                nodes=nodes,
                edges=edges,
                parsed_rec=parsed_rec,
                company_name_to_id=company_name_to_id,
                company_node_id=company_node_id,
                stock_code=stock_code,
                event_id=event_id,
                event_date=event_date,
                parsed_meeting_date=parsed_meeting_date,
                disclosure_phase=disclosure_phase,
                acpt_no=acpt_no,
                document_title=doc_title,
                disclosed_date=disclosed_str,
                source_file=rel_src_file,
                metadata=metadata,
            )

    _reconcile_shareholder_terminations(nodes, edges)


def export_ontology_to_web_json(
    nodes: Dict[str, GraphNode],
    edges: List[GraphEdge],
    output_path: str | Path,
    metadata: Dict[str, Any] | None = None,
) -> None:
    """Export ontology nodes and edges to flat, web-friendly JSON format with metadata."""
    web_nodes = []
    for node_id, node in nodes.items():
        # Subclass type name (e.g. 'Company', 'IssuanceEvent')
        type_name = node.__class__.__name__
        
        # Display name / label
        name = getattr(node, "name", getattr(node, "security_type", getattr(node, "usage_type", getattr(node, "issuance_type", node_id))))
        if type_name == "ShareholderMeeting":
            name = getattr(node, "meeting_type", "\uc8fc\uc8fc\ucd1d\ud68c")

        # properties
        props = node.properties.copy()
        # copy attributes from subclass
        for field_name in node.__class__.model_fields:
            if field_name not in ("id", "labels", "properties"):
                val = getattr(node, field_name)
                if isinstance(val, (date, datetime)):
                    val = val.isoformat()
                props[field_name] = val

        web_nodes.append({
            "id": node.id,
            "label": name,
            "type": type_name,
            "group": type_name,
            "tags": node.labels,
            "properties": props,
        })

    web_edges = []
    for idx, edge in enumerate(edges):
        props = edge.properties.copy()
        for field_name in edge.__class__.model_fields:
            if field_name not in ("id", "source_id", "target_id", "edge_type", "properties"):
                val = getattr(edge, field_name)
                if isinstance(val, (date, datetime)):
                    val = val.isoformat()
                props[field_name] = val

        web_edges.append({
            "id": edge.id or f"edge_{idx}_{uuid.uuid4().hex[:6]}",
            "source": edge.source_id,
            "target": edge.target_id,
            "relation": edge.edge_type,
            "category": edge.edge_type,
            "weight": edge.weight or 0.0,
            "directed": True,
            "properties": props,
        })

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    out_data = {
        "format": "finiq_disclosure_graph_v1",
        "metadata": metadata or {},
        "nodes": web_nodes,
        "edges": web_edges
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out_data, f, ensure_ascii=False, indent=2)
