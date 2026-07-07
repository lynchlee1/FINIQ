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
    """Pad stock/company code to 6 digits (e.g. '22180' -> '022180')."""
    if not company_id:
        return ""
    digits = "".join(char for char in str(company_id) if char.isdigit())
    return digits.zfill(6) if digits else ""


def parse_date_safe(date_str: str | None) -> date:
    """Safely parse date strings (ISO, Korean, or fallback)."""
    if not date_str:
        return date(1900, 1, 1)
    
    date_str = str(date_str).strip()
    if len(date_str) >= 10:
        try:
            return date.fromisoformat(date_str[:10])
        except ValueError:
            pass

    # Match YYYY년 MM월 DD일
    try:
        match = re.search(r"(\d{4})[년\-\./\s]+(\d{1,2})[월\-\./\s]+(\d{1,2})", date_str)
        if match:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except Exception:
        pass

    return date(1900, 1, 1)


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
        r"\(주\)", r"주식회사",
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
) -> Tuple[Dict[str, GraphNode], List[GraphEdge]]:
    """Build ontology graph components (nodes and edges) from parsed files."""
    nodes: Dict[str, GraphNode] = {}
    edges: List[GraphEdge] = []

    # Map normalized names of all companies to their stock_code node ID
    # This enables Entity Resolution to merge corporate investors with company nodes!
    company_name_to_id: Dict[str, str] = {}
    
    def index_companies(f_path):
        if not f_path or not Path(f_path).exists():
            return
        try:
            with open(f_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                disclosures = data.get("disclosures", [])
                for d in disclosures:
                    raw_id = d.get("company_id") or d.get("company_key")
                    code = normalize_company_id(raw_id)
                    name = d.get("company_name") or d.get("submitter")
                    if code and name:
                        norm_name = normalize_entity_name(name)
                        company_name_to_id[norm_name] = f"company_{code}"
        except Exception:
            pass

    index_companies(rights_filtered_path)
    index_companies(bond_filtered_path)
    index_companies(shareholder_meeting_filtered_path)

    # 1. Process Rights Issuance (유무상증자)
    _process_rights_issuance(
        nodes, edges, rights_issuance_path, rights_filtered_path, company_name_to_id
    )

    # 2. Process Bond Issuance (채권발행)
    _process_bond_issuance(
        nodes, edges, bond_issuance_path, bond_filtered_path, company_name_to_id
    )

    # 3. Process Shareholder Meetings (주주총회)
    _process_shareholder_meetings(
        nodes, edges, shareholder_meeting_filtered_path, shareholder_meeting_parsed_path
    )

    return nodes, edges


def _process_rights_issuance(
    nodes: Dict[str, GraphNode],
    edges: List[GraphEdge],
    parsed_path: str | Path | None,
    filtered_path: str | Path | None,
    company_name_to_id: Dict[str, str],
) -> None:
    if parsed_path is None:
        return
    parsed_path = Path(parsed_path)
    if not parsed_path.exists():
        return

    # Load filtered data for company metadata mapping
    filtered_map = {}
    if filtered_path and Path(filtered_path).exists():
        try:
            with open(filtered_path, "r", encoding="utf-8") as f:
                filtered_data = json.load(f)
                for disc in filtered_data.get("disclosures", []):
                    acpt = disc.get("acpt_no")
                    if acpt:
                        filtered_map[acpt] = disc
        except Exception:
            pass

    try:
        with open(parsed_path, "r", encoding="utf-8") as f:
            parsed_data = json.load(f)
            records = parsed_data.get("records", [])
    except Exception:
        return

    for rec in records:
        acpt_no = rec.get("acpt_no")
        if not acpt_no:
            continue

        # Get metadata
        meta = filtered_map.get(acpt_no, {})
        raw_company_id = meta.get("company_id") or meta.get("company_key")
        stock_code = normalize_company_id(raw_company_id)
        company_name = meta.get("company_name") or rec.get("기업명(발행사)") or meta.get("submitter") or "알수없음"

        if not stock_code:
            continue

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

        # Create Issuance Event
        event_date = parse_date_safe(meta.get("disclosed_date") or meta.get("disclosed_at") or rec.get("납입일"))
        event_id = f"issuance_event_{acpt_no}"
        issuance_type = rec.get("증자유형") or "유상증자"
        
        nodes[event_id] = IssuanceEvent(
            id=event_id,
            event_date=event_date,
            issuance_type=issuance_type,
            properties={
                "title": rec.get("title", ""),
                "증자방식": rec.get("증자방식", ""),
                "납입일": rec.get("납입일", ""),
                "상장예정일": rec.get("상장예정일", ""),
                "신주권교부예정일": rec.get("신주권교부예정일", ""),
                "acpt_no": acpt_no,
                "doc_no": rec.get("doc_no", ""),
            }
        )

        # Edge: Company -[EXECUTED]-> IssuanceEvent
        edges.append(
            GraphEdge(
                source_id=company_node_id,
                target_id=event_id,
                edge_type=EdgeTypes.EXECUTED,
                start_date=event_date,
                document_type="유무상증자결정",
                source_url=make_relative_path(rec.get("source_file")),
            )
        )

        # Extract Securities issued
        security_prices = {sec_type: price for sec_type, price in rec.get("발행가액", [])}
        main_security_node_id = None

        for sec_type, count in rec.get("신주의 종류와 수", []):
            if not count or count <= 0:
                continue
            
            sec_id = f"security_{acpt_no}_{sec_type}"
            price = security_prices.get(sec_type, 0)
            
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
                )
            )

        # Extract Fund Usages
        for usage_type, amount in rec.get("발행목적", []):
            if not amount or amount <= 0:
                continue
            
            usage_id = f"fund_usage_{acpt_no}_{usage_type}"
            nodes[usage_id] = FundUsage(
                id=usage_id,
                usage_type=usage_type,
                planned_amount=float(amount),
                properties={
                    "currency": "KRW"
                }
            )

            # Edge: IssuanceEvent -[FOR_PURPOSE]-> FundUsage
            edges.append(
                GraphEdge(
                    source_id=event_id,
                    target_id=usage_id,
                    edge_type=EdgeTypes.FOR_PURPOSE,
                    start_date=event_date,
                    weight=float(amount),
                )
            )

        # Extract Investors
        for target_name, target_shares in rec.get("발행대상자", []):
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
                if inv_type == "Person":
                    # Disambiguation: Scope individual investors to prevent cross-company homonym pollution.
                    investor_id = f"person_{stock_code}_{norm_name}"
                    if investor_id not in nodes:
                        nodes[investor_id] = Person(
                            id=investor_id,
                            name=target_name,
                            properties={"normalized_name": norm_name, "scoped_company": stock_code}
                        )
                elif inv_type == "Company":
                    investor_id = f"company_inv_{norm_name}"
                    if investor_id not in nodes:
                        nodes[investor_id] = Company(
                            id=investor_id,
                            name=target_name,
                            properties={"normalized_name": norm_name, "is_unlisted": True}
                        )
                else:
                    investor_id = f"org_{norm_name}"
                    if investor_id not in nodes:
                        nodes[investor_id] = Organization(
                            id=investor_id,
                            name=target_name,
                            properties={"normalized_name": norm_name}
                        )

            # Edge: Investor -[ACQUIRED]-> Security (prefer main security, or fallback to event_id)
            target_node_id = main_security_node_id or event_id
            edges.append(
                GraphEdge(
                    source_id=investor_id,
                    target_id=target_node_id,
                    edge_type=EdgeTypes.ACQUIRED,
                    start_date=event_date,
                    weight=float(shares),
                    document_type="유무상증자결정",
                    properties={
                        "acpt_no": acpt_no,
                        "shares": shares,
                    }
                )
            )


def _process_bond_issuance(
    nodes: Dict[str, GraphNode],
    edges: List[GraphEdge],
    parsed_path: str | Path | None,
    filtered_path: str | Path | None,
    company_name_to_id: Dict[str, str],
) -> None:
    if parsed_path is None:
        return
    parsed_path = Path(parsed_path)
    if not parsed_path.exists():
        return

    # Load filtered data for company metadata mapping
    filtered_map = {}
    if filtered_path and Path(filtered_path).exists():
        try:
            with open(filtered_path, "r", encoding="utf-8") as f:
                filtered_data = json.load(f)
                for disc in filtered_data.get("disclosures", []):
                    acpt = disc.get("acpt_no")
                    if acpt:
                        filtered_map[acpt] = disc
        except Exception:
            pass

    try:
        with open(parsed_path, "r", encoding="utf-8") as f:
            parsed_data = json.load(f)
            records = parsed_data.get("records", [])
    except Exception:
        return

    for rec in records:
        acpt_no = rec.get("acpt_no")
        if not acpt_no:
            continue

        meta = filtered_map.get(acpt_no, {})
        raw_company_id = meta.get("company_id") or meta.get("company_key")
        stock_code = normalize_company_id(raw_company_id)
        company_name = rec.get("기업명(발행사)") or meta.get("company_name") or meta.get("submitter") or "알수없음"

        if not stock_code:
            continue

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

        # Create Issuance Event
        event_date = parse_date_safe(meta.get("disclosed_date") or meta.get("disclosed_at") or rec.get("납입일"))
        event_id = f"issuance_event_{acpt_no}"
        bond_type = rec.get("종류") or "사채"
        
        nodes[event_id] = IssuanceEvent(
            id=event_id,
            event_date=event_date,
            issuance_type=f"{bond_type}발행",
            properties={
                "title": rec.get("title", ""),
                "회차": rec.get("회차", ""),
                "발행금액": rec.get("발행금액", 0),
                "납입일": rec.get("납입일", ""),
                "만기일": rec.get("만기일", ""),
                "행사가액": rec.get("행사가액", 0),
                "사채발행방법": rec.get("사채발행방법", ""),
                "acpt_no": acpt_no,
            }
        )

        # Edge: Company -[EXECUTED]-> IssuanceEvent
        edges.append(
            GraphEdge(
                source_id=company_node_id,
                target_id=event_id,
                edge_type=EdgeTypes.EXECUTED,
                start_date=event_date,
                document_type="사채발행결정",
                source_url=make_relative_path(rec.get("source_file")),
            )
        )

        # Create Security node
        sec_id = f"security_{acpt_no}"
        sec_type = f"제{rec.get('회차', '') or '0'}회차 {bond_type}"
        amount = rec.get("발행금액")
        
        nodes[sec_id] = Security(
            id=sec_id,
            security_type=sec_type,
            amount=int(amount) if amount else None,
            properties={
                " 만기일": rec.get("만기일", ""),
                "행사가액": rec.get("행사가액", 0),
            }
        )

        # Edge: IssuanceEvent -[ISSUED]-> Security
        edges.append(
            GraphEdge(
                source_id=event_id,
                target_id=sec_id,
                edge_type=EdgeTypes.ISSUED,
                start_date=event_date,
                weight=float(amount) if amount else None,
            )
        )

        # Extract Fund Usages
        for usage_type, usage_amount in rec.get("발행목적", []):
            if not usage_amount or usage_amount <= 0:
                continue
            
            usage_id = f"fund_usage_{acpt_no}_{usage_type}"
            nodes[usage_id] = FundUsage(
                id=usage_id,
                usage_type=usage_type,
                planned_amount=float(usage_amount),
            )

            # Edge: IssuanceEvent -[FOR_PURPOSE]-> FundUsage
            edges.append(
                GraphEdge(
                    source_id=event_id,
                    target_id=usage_id,
                    edge_type=EdgeTypes.FOR_PURPOSE,
                    start_date=event_date,
                    weight=float(usage_amount),
                )
            )

        # Extract Investors
        for target_name, target_amount in rec.get("투자자", []):
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
                if inv_type == "Person":
                    # Disambiguation: Scope individual investors to prevent cross-company homonym pollution.
                    investor_id = f"person_{stock_code}_{norm_name}"
                    if investor_id not in nodes:
                        nodes[investor_id] = Person(
                            id=investor_id,
                            name=target_name,
                            properties={"normalized_name": norm_name, "scoped_company": stock_code}
                        )
                elif inv_type == "Company":
                    investor_id = f"company_inv_{norm_name}"
                    if investor_id not in nodes:
                        nodes[investor_id] = Company(
                            id=investor_id,
                            name=target_name,
                            properties={"normalized_name": norm_name, "is_unlisted": True}
                        )
                else:
                    investor_id = f"org_{norm_name}"
                    if investor_id not in nodes:
                        nodes[investor_id] = Organization(
                            id=investor_id,
                            name=target_name,
                            properties={"normalized_name": norm_name}
                        )

            # Edge: Investor -[ACQUIRED]-> Security
            edges.append(
                GraphEdge(
                    source_id=investor_id,
                    target_id=sec_id,
                    edge_type=EdgeTypes.ACQUIRED,
                    start_date=event_date,
                    weight=amount_val,
                    document_type="사채발행결정",
                    properties={
                        "acpt_no": acpt_no,
                        "amount": amount_val,
                    }
                )
            )


def _process_shareholder_meetings(
    nodes: Dict[str, GraphNode],
    edges: List[GraphEdge],
    filtered_path: str | Path | None,
    parsed_path: str | Path | None = None,
) -> None:
    if filtered_path is None:
        return
    filtered_path = Path(filtered_path)
    if not filtered_path.exists():
        return

    # Load parsed data if provided
    parsed_map = {}
    if parsed_path and Path(parsed_path).exists():
        try:
            with open(parsed_path, "r", encoding="utf-8") as f:
                parsed_data = json.load(f)
                records = parsed_data.get("records", [])
                for rec in records:
                    acpt = rec.get("acpt_no")
                    if acpt:
                        parsed_map[acpt] = rec
        except Exception:
            pass

    try:
        with open(filtered_path, "r", encoding="utf-8") as f:
            filtered_data = json.load(f)
            disclosures = filtered_data.get("disclosures", [])
    except Exception:
        return

    for disc in disclosures:
        acpt_no = disc.get("acpt_no")
        if not acpt_no:
            continue

        raw_company_id = disc.get("company_id") or disc.get("company_key")
        stock_code = normalize_company_id(raw_company_id)
        company_name = disc.get("company_name") or disc.get("submitter") or "알수없음"

        if not stock_code:
            continue

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

        # Create Shareholder Meeting Event
        event_date = parse_date_safe(disc.get("disclosed_date") or disc.get("disclosed_at"))
        event_id = f"shareholder_meeting_{acpt_no}"
        
        # Inferred type
        title = disc.get("title", "")
        meeting_type = "정기주주총회" if "정기" in title else ("임시주주총회" if "임시" in title else "주주총회")

        nodes[event_id] = ShareholderMeeting(
            id=event_id,
            event_date=event_date,
            meeting_type=meeting_type,
            properties={
                "title": title,
                "acpt_no": acpt_no,
            }
        )

        # Edge: Company -[HELD]-> ShareholderMeeting
        edges.append(
            GraphEdge(
                source_id=company_node_id,
                target_id=event_id,
                edge_type=EdgeTypes.HELD,
                start_date=event_date,
                document_type="주주총회공시",
            )
        )

        # Process parsed details if available
        parsed_rec = parsed_map.get(acpt_no)
        if parsed_rec:
            # 1. Extract Agendas (의안)
            agendas = parsed_rec.get("agendas", [])
            for idx, agenda_title in enumerate(agendas):
                agenda_title = agenda_title.strip()
                if not agenda_title:
                    continue
                agenda_id = f"agenda_{acpt_no}_{idx}"
                nodes[agenda_id] = Agenda(
                    id=agenda_id,
                    title=agenda_title,
                    properties={"index": idx}
                )
                # Edge: ShareholderMeeting -[INCLUDES]-> Agenda
                edges.append(
                    GraphEdge(
                        source_id=event_id,
                        target_id=agenda_id,
                        edge_type=EdgeTypes.INCLUDES,
                        start_date=event_date,
                    )
                )
                
            # 2. Extract Nominated/Elected Directors & Auditors
            elections = parsed_rec.get("elections", [])
            for elec in elections:
                name = elec.get("name") or elec.get("candidate_name")
                if not name:
                    continue
                name = name.strip()
                norm_name = normalize_entity_name(name)
                person_id = f"person_{stock_code}_{norm_name}"
                
                if person_id not in nodes:
                    nodes[person_id] = Person(
                        id=person_id,
                        name=name,
                        properties={"normalized_name": norm_name, "scoped_company": stock_code}
                    )
                
                # Edge: Person -[DIRECTOR_OF]-> Company
                edges.append(
                    GraphEdge(
                        source_id=person_id,
                        target_id=company_node_id,
                        edge_type=EdgeTypes.DIRECTOR_OF,
                        start_date=event_date,
                        properties={
                            "role": elec.get("role", "이사"),
                            "is_outside": elec.get("is_outside", False),
                            "acpt_no": acpt_no,
                        }
                    )
                )


def export_ontology_to_web_json(
    nodes: Dict[str, GraphNode],
    edges: List[GraphEdge],
    output_path: str | Path,
) -> None:
    """Export ontology nodes and edges to flat, web-friendly JSON format."""
    web_nodes = []
    for node_id, node in nodes.items():
        # Subclass type name (e.g. 'Company', 'IssuanceEvent')
        type_name = node.__class__.__name__
        
        # Display name / label
        name = getattr(node, "name", getattr(node, "security_type", getattr(node, "usage_type", getattr(node, "issuance_type", node_id))))
        if type_name == "ShareholderMeeting":
            name = getattr(node, "meeting_type", "주주총회")

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
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"nodes": web_nodes, "edges": web_edges}, f, ensure_ascii=False, indent=2)



