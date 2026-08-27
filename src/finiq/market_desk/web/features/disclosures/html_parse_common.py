"""KIND disclosure HTML parsing helpers for the web UI."""

from __future__ import annotations

import json
import tempfile
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from datetime import datetime
from inspect import signature
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from finiq.concurrency import resolve_worker_count
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    atomic_write_json,
    validate_workspace_mode,
)
from finiq.market_desk.web.features.disclosures.html_common import (
    _internal_html_source_unavailable_placeholder_file,
    _load_workspace_filtered_payload,
    collect_acpt_numbers_from_json,
)
from finiq.market_desk.web.features.market_data.service_common import (
    _record_filter_blocks_match,
    _validate_filter_blocks,
)
from finiq.market_desk.web.html_parsers import (
    parse_asset_transaction,
    parse_bond_issuance,
    parse_rights_issuance,
    parse_security_transaction,
    parse_shareholder_meeting,
)
from finiq.market_desk.web.html_parsers.common import (
    build_base_record,
)

ParseFunction = Callable[..., dict[str, Any]]
ProgressCallback = Callable[[str], None]
_CANCELLED_PARSES: set[str] = set()
_CANCEL_LOCK = Lock()
_PARSE_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = Lock()
SUPPORTED_RECORD_FILTER_OPERATORS = {"contains", "equals", "exists", "in"}

@dataclass(frozen=True)
class ParseFilterConfig:
    """One reusable parsed-field filter exposed by 공시원문 변환."""

    field: str
    status_label: str


@dataclass(frozen=True)
class ParserMethodConfig:
    """Parser metadata shared by parse, preview, filters, and UI payloads."""

    key: str
    label: str
    status: str
    description: str
    parser: ParseFunction
    filters: tuple[ParseFilterConfig, ...] = ()
    reporting_company_field: str | None = None


PARSER_METHOD_CONFIGS = {
    "bond_issuance": ParserMethodConfig(
        key="bond_issuance",
        label="사채발행파싱",
        status="상세 필드 지원",
        description="메자닌 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
        parser=parse_bond_issuance,
        filters=(ParseFilterConfig(field="사채발행방법", status_label="사채발행방법"),),
        reporting_company_field="corp_name",
    ),
    "rights_issuance": ParserMethodConfig(
        key="rights_issuance",
        label="유무상증자파싱",
        status="상세 필드 지원",
        description="유상증자 및 무상증자 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
        parser=parse_rights_issuance,
        filters=(ParseFilterConfig(field="증자방식", status_label="증자방식"),),
        reporting_company_field="corp_name",
    ),
    "shareholder_meeting": ParserMethodConfig(
        key="shareholder_meeting",
        label="주주총회파싱",
        status="원본 테이블 구조 지원",
        description="주주총회 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
        parser=parse_shareholder_meeting,
    ),
    "asset_transaction": ParserMethodConfig(
        key="asset_transaction",
        label="유무형자산거래파싱",
        status="원본 테이블 구조 지원",
        description="유형자산 및 무형자산 거래 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
        parser=parse_asset_transaction,
    ),
    "security_transaction": ParserMethodConfig(
        key="security_transaction",
        label="발행증권거래파싱",
        status="원본 테이블 구조 지원",
        description="발행증권 거래 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
        parser=parse_security_transaction,
    ),
}

PARSER_REGISTRY = {
    key: config.parser for key, config in PARSER_METHOD_CONFIGS.items()
}


def list_parser_methods_payload() -> dict[str, Any]:
    return {
        "format": "finiq_disclosure_parser_methods_v1",
        "methods": [
            {
                "key": config.key,
                "label": config.label,
                "status": config.status,
                "description": config.description,
                "filters": [
                    {"field": item.field, "status_label": item.status_label}
                    for item in config.filters
                ],
            }
            for config in PARSER_METHOD_CONFIGS.values()
        ],
    }


@dataclass(frozen=True)
class ParseRequest:
    """Validated options for one HTML parse run."""

    mode: str
    parser_method: str
    parser: ParseFunction
    reporting_company_field: str | None
    input_directory: Path
    output_path: Path
    html_files: list[Path]
    metadata_index: dict[str, dict[str, Any]]
    families: dict[str, dict[str, Any]]
    limit: int | None
    skip_errors: bool
    progress_interval: int
    parallel_workers: int
    cancel_token: str | None
    cancel_check: Callable[[], bool] | None
    filter_blocks: list[dict[str, Any]]
    record_filters: list[dict[str, Any]]


@dataclass
class ParseRunState:
    """Mutable parse run state that is eventually serialized as the result JSON."""

    progress_callback: ProgressCallback | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    processed_this_run: int = 0

    def emit(self, message: str) -> None:
        if self.progress_callback is not None:
            self.progress_callback(message)


BOND_SUMMARY_FIELDS = (
    "corp_name",
    "회차",
    "종류",
    "기업명(행사대상)",
    "상장구분",
    "발행금액",
    "행사가액",
    "납입일",
    "만기일",
    "사채발행방법",
    "행사시작일",
    "행사종료일",
    "투자자",
)
CHANGE_LOG_COMPARISON_FIELDS = {
    "bond_issuance": (
        "corp_name",
        "회차",
        "종류",
        "기업명(행사대상)",
        "상장구분",
        "발행금액",
        "행사가액",
        "납입일",
        "만기일",
        "사채발행방법",
        "행사시작일",
        "행사종료일",
        "투자자",
    ),
    "rights_issuance": (
        "corp_name",
        "상장구분",
        "신주의 종류와 수",
        "증자 전 발행주식총수",
        "발행목적",
        "발행가액",
        "증자방식",
        "납입일",
        "신주권교부예정일",
        "상장예정일",
        "발행대상자",
    ),
}
DEFAULT_CHANGE_LOG_DATE_THRESHOLDS = {
    "만기일": 3,
    "행사시작일": 3,
    "행사종료일": 3,
    "납입일": 3,
    "신주권교부예정일": 3,
    "상장예정일": 3,
    "기준일": 3,
    "권리배정기준일": 3,
}
DEFAULT_CHANGE_LOG_NUMERIC_THRESHOLDS = {
    "발행금액": 1,
    "발행가액": 1,
    "행사가액": 1,
    "신주의 종류와 수": 1,
}
MAJOR_CHANGE_FIELDS = {
    "bond_issuance": {
        "corp_name",
        "종류",
        "기업명(행사대상)",
        "상장구분",
        "발행금액",
        "행사가액",
        "납입일",
        "만기일",
        "사채발행방법",
        "행사시작일",
        "행사종료일",
        "투자자",
    },
    "rights_issuance": {
        "corp_name",
        "신주의 종류와 수",
        "증자 전 발행주식총수",
        "발행목적",
        "발행가액",
        "증자방식",
        "납입일",
        "신주권교부예정일",
        "상장예정일",
        "발행대상자",
    },
}

# Fields that should always be excluded from change detection as they are metadata
METADATA_FIELDS = {
    "title",
    "acpt_no",
    "family_id",
    "current_sequence",
    "family_member_count",
    "raw_tables",
    "index",
}
# The table cap bounds rendered components even when tables are short or empty;
# the row cap independently bounds the preview response size.
SOURCE_PREVIEW_MAX_TABLES = 12
SOURCE_PREVIEW_MAX_ROWS = 120


def _normalize_listing_market(value: Any) -> str:
    market = str(value or "").strip()
    if market == "유가증권":
        return "코스피"
    return market


def _load_html_parse_metadata(
    input_directory: Path,
    *,
    filtered_metadata_path: Path | None = None,
    compressed_metadata_path: Path | None = None,
    allowed_acpt_numbers: set[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    metadata_index: dict[str, dict[str, Any]] = {}
    families: dict[str, dict[str, Any]] = {}
    filtered_metadata_index: dict[str, dict[str, Any]] = {}
    compressed_metadata_index: dict[str, dict[str, Any]] = {}
    if filtered_metadata_path is not None:
        filtered_metadata_index = _load_filtered_metadata_index(filtered_metadata_path)
    if compressed_metadata_path is not None:
        (
            compressed_metadata_index,
            compressed_families,
        ) = _load_compressed_external_html_metadata_index(
            compressed_metadata_path,
            allowed_acpt_numbers=allowed_acpt_numbers,
        )
        families.update(compressed_families)
    for acpt_no in sorted(set(filtered_metadata_index) | set(compressed_metadata_index)):
        metadata = filtered_metadata_index.pop(acpt_no, {})
        metadata.update(compressed_metadata_index.pop(acpt_no, {}))
        metadata_index[acpt_no] = metadata
    return metadata_index, families


def _filtered_metadata_item(item: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    acpt_no = str(item.get("acpt_no") or "").strip()
    if not acpt_no:
        raise ValueError("filtered metadata acpt_no must not be empty")
    return acpt_no, {
        "market": _normalize_listing_market(item.get("market")),
        "company_name": str(item.get("company_name") or "").strip(),
        "disclosed_at": str(item.get("disclosed_at") or "").strip(),
    }


def _compressed_external_html_metadata_item(
    item: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    acpt_no = str(item.get("acpt_no") or "").strip()
    if not acpt_no:
        raise ValueError("compressed metadata acpt_no must not be empty")
    selected_main_doc_no = str(item.get("selected_main_doc_no") or "").strip()
    return acpt_no, {
        "title": str(item.get("title") or "").strip(),
        "doc_no": selected_main_doc_no,
        "selected_main_doc_no": selected_main_doc_no,
    }


def _load_filtered_metadata_index(filtered_path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(filtered_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"필터 결과 JSON을 읽을 수 없습니다: {filtered_path}") from exc
    if not isinstance(payload, dict) or payload.get("format") != "kind_disclosure_filter_v1":
        raise ValueError(f"필터 결과 JSON 형식이 올바르지 않습니다: {filtered_path}")
    metadata_index: dict[str, dict[str, Any]] = {}
    disclosures = payload.get("disclosures")
    if not isinstance(disclosures, list):
        raise ValueError(f"필터 결과 disclosures가 배열이 아닙니다: {filtered_path}")
    for index, item in enumerate(disclosures):
        if not isinstance(item, dict):
            raise ValueError(f"filtered disclosures[{index}] must be an object")
        parsed = _filtered_metadata_item(item)
        acpt_no, metadata = parsed
        if acpt_no in metadata_index:
            raise ValueError(f"duplicate KIND metadata acpt_no: {acpt_no}")
        metadata_index[acpt_no] = metadata
    return metadata_index


def _load_compressed_external_html_metadata_index(
    compressed_path: Path,
    *,
    allowed_acpt_numbers: set[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    try:
        payload = json.loads(compressed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"외부 HTML 압축 JSON을 읽을 수 없습니다: {compressed_path}"
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("format") != "finiq_disclosure_external_html_docs_v1"
    ):
        raise ValueError(f"외부 HTML 압축 JSON 형식이 올바르지 않습니다: {compressed_path}")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError(f"외부 HTML 압축 records가 배열이 아닙니다: {compressed_path}")
    selected_doc_to_record: dict[str, dict[str, Any]] = {}
    selected_records: list[dict[str, Any]] = []
    for index, item in enumerate(records):
        if not isinstance(item, dict):
            raise ValueError(f"compressed records[{index}] must be an object")
        acpt_no = str(item.get("acpt_no") or "").strip()
        if allowed_acpt_numbers is not None and acpt_no not in allowed_acpt_numbers:
            continue
        if not isinstance(item.get("metadata"), dict):
            raise ValueError(f"compressed records[{index}].metadata must be an object")
        selected_doc_no = str(item.get("selected_main_doc_no") or "").strip()
        if not selected_doc_no:
            raise ValueError(f"compressed records[{index}].selected_main_doc_no is required")
        if selected_doc_no in selected_doc_to_record:
            raise ValueError(
                f"duplicate external metadata selected_main_doc_no: {selected_doc_no}"
            )
        selected_doc_to_record[selected_doc_no] = item
        selected_records.append(item)
    metadata_index: dict[str, dict[str, Any]] = {}
    families: dict[str, dict[str, Any]] = {}
    for item in selected_records:
        parsed = _compressed_external_html_metadata_item(item)
        acpt_no, metadata = parsed
        if acpt_no in metadata_index:
            raise ValueError(f"duplicate external metadata acpt_no: {acpt_no}")
        family = _external_html_correction_family(item, selected_doc_to_record)
        if family is not None:
            family_id, current_sequence, members = family
            metadata["family_id"] = family_id
            metadata["current_sequence"] = current_sequence
            metadata["family_member_count"] = len(members)
            families.setdefault(family_id, {"members": members})
        metadata_index[acpt_no] = metadata
    return metadata_index, families


def _external_html_correction_family(
    item: dict[str, Any],
    selected_doc_to_record: dict[str, dict[str, Any]],
) -> tuple[str, int, list[dict[str, Any]]] | None:
    main_docs = [
        doc
        for doc in item.get("docs") or []
        if isinstance(doc, dict)
        and str(doc.get("select_id") or "").strip() == "mainDoc"
        and str(doc.get("doc_no") or "").strip()
    ]
    if len(main_docs) < 2:
        return None

    members: list[dict[str, Any]] = []
    for sequence, doc in enumerate(sorted(main_docs, key=_external_main_doc_sort_key)):
        doc_no = str(doc.get("doc_no") or "").strip()
        member_record = selected_doc_to_record.get(doc_no)
        if member_record is None:
            return None
        metadata = member_record["metadata"]
        disclosed_at = str(metadata.get("disclosed_at") or "").strip()
        if not disclosed_at:
            raise ValueError(
                f"correction family metadata.disclosed_at is required: doc_no={doc_no}"
            )
        title = str(doc.get("text") or "").strip()
        members.append(
            {
                "sequence": sequence,
                "acpt_no": str(member_record.get("acpt_no") or ""),
                "doc_no": doc_no,
                "title": title,
                "disclosed_at": disclosed_at,
                "is_correction_report": _external_doc_is_correction(doc, title),
            }
        )

    current_doc_no = str(item.get("selected_main_doc_no") or "").strip()
    current_sequence = next(
        (
            member["sequence"]
            for member in members
            if str(member.get("doc_no") or "") == current_doc_no
        ),
        None,
    )
    family_id = str(members[-1].get("acpt_no") or "")
    if current_sequence is None or not family_id:
        return None
    return family_id, current_sequence, members


def _external_main_doc_sort_key(doc: dict[str, Any]) -> tuple[int, str]:
    option_index = int(doc["option_index"])
    return (option_index, str(doc.get("doc_no") or ""))


def _external_doc_is_correction(doc: dict[str, Any], title: str) -> bool:
    text = str(doc.get("text") or "")
    return "정정" in text or "정정" in title


def _apply_parse_metadata(
    record: dict[str, Any],
    metadata_index: dict[str, dict[str, Any]],
    *,
    reporting_company_field: str | None,
) -> dict[str, Any]:
    acpt_no = str(record.get("acpt_no") or "")
    metadata = metadata_index.get(acpt_no) or {}
    market = metadata.get("market")
    company_name = metadata.get("company_name")
    disclosed_at = str(metadata.get("disclosed_at") or "").strip()
    doc_no = metadata.get("doc_no")
    family_id = str(metadata.get("family_id") or "")
    current_sequence = metadata.get("current_sequence")
    family_member_count = metadata.get("family_member_count")
    if (
        not market
        and not company_name
        and not disclosed_at
        and not doc_no
        and not family_id
    ):
        return record
    updated_record = dict(record)
    if disclosed_at:
        updated_record["disclosed_at"] = disclosed_at
    if doc_no and not updated_record.get("doc_no"):
        updated_record["doc_no"] = doc_no
    if (
        family_id
        and isinstance(current_sequence, int)
        and isinstance(family_member_count, int)
    ):
        updated_record["family_id"] = family_id
        updated_record["current_sequence"] = current_sequence
        updated_record["family_member_count"] = family_member_count
    if market:
        updated_record["상장구분"] = market
    if reporting_company_field and company_name:
        updated_record[reporting_company_field] = company_name
    return updated_record


def cancel_disclosure_html_parse(token: str) -> dict[str, Any]:
    normalized_token = str(token or "").strip()
    if not normalized_token:
        msg = "cancel_token is required"
        raise ValueError(msg)
    with _CANCEL_LOCK:
        _CANCELLED_PARSES.add(normalized_token)
    return {"cancelled": True, "cancel_token": normalized_token}


def _clear_cancel_token(token: str | None) -> None:
    if not token:
        return
    with _CANCEL_LOCK:
        _CANCELLED_PARSES.discard(token)


def _is_cancelled(token: str | None) -> bool:
    if not token:
        return False
    with _CANCEL_LOCK:
        return token in _CANCELLED_PARSES


def _parse_cancelled(request: ParseRequest) -> bool:
    return _is_cancelled(request.cancel_token) or bool(
        request.cancel_check and request.cancel_check()
    )


def _parse_limit(value: Any) -> int | None:
    if value in (None, ""):
        return None
    parsed = int(value)
    if parsed < 1:
        msg = "limit must be >= 1"
        raise ValueError(msg)
    return parsed


def _parse_progress_interval(value: Any) -> int:
    if value in (None, ""):
        return 1000
    parsed = int(value)
    if parsed < 1:
        msg = "progress_interval must be >= 1"
        raise ValueError(msg)
    return parsed


def _parse_parallel_workers(value: Any, total_files: int) -> int:
    return resolve_worker_count(
        value,
        item_count=total_files,
        field_name="parallel_workers",
    )


def _collect_html_files(
    input_directory: Path,
    limit: int | None,
    *,
    allowed_acpt_numbers: set[str] | None = None,
) -> list[Path]:
    resolved_root = input_directory.resolve()
    year_directories = sorted(
        path
        for path in resolved_root.iterdir()
        if path.is_dir() and len(path.name) == 4 and path.name.isdigit()
    )
    candidates = [
        path
        for year_directory in year_directories
        for path in year_directory.glob("*.html")
    ]
    resolved_files: set[Path] = set()
    for path in candidates:
        resolved_path = path.resolve()
        try:
            relative_path = resolved_path.relative_to(resolved_root)
        except ValueError:
            continue
        if (
            len(relative_path.parts) == 2
            and len(relative_path.parts[0]) == 4
            and relative_path.parts[0].isdigit()
            and resolved_path.suffix.lower() == ".html"
            and resolved_path.is_file()
            and (
                allowed_acpt_numbers is None
                or resolved_path.stem in allowed_acpt_numbers
            )
        ):
            resolved_files.add(resolved_path)

    files = sorted(resolved_files)
    stems: set[str] = set()
    for path in files:
        if path.stem in stems:
            msg = f"duplicate HTML filename stem: {path.stem}"
            raise ValueError(msg)
        stems.add(path.stem)
    return files[:limit] if limit is not None else files


def _parse_record_filters(value: Any) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("record_filters must be a list")
    filters: list[dict[str, Any]] = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"record_filters[{index}] must be an object")
        field = str(item.get("field") or "").strip()
        if not field:
            raise ValueError(f"record_filters[{index}].field is required")
        operator = str(item.get("operator") or "contains").strip()
        if operator not in SUPPORTED_RECORD_FILTER_OPERATORS:
            raise ValueError(
                f"record_filters[{index}].operator is unsupported: {operator}"
            )
        raw_value = item.get("value")
        if operator == "in":
            values = [
                str(candidate).strip()
                for candidate in raw_value
                if str(candidate).strip()
            ] if isinstance(raw_value, list) else []
            if not values:
                raise ValueError(
                    f"record_filters[{index}].value must be a non-empty list for operator in"
                )
            filters.append({"field": field, "operator": operator, "value": values})
            continue
        filter_value = "" if raw_value is None else str(raw_value).strip()
        if operator != "exists" and not filter_value:
            raise ValueError(f"record_filters[{index}].value is required")
        filters.append({"field": field, "operator": operator, "value": filter_value})
    return filters


def _parse_filter_blocks(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    return _validate_filter_blocks(value)


def _parse_skip_errors(body: dict[str, Any]) -> bool:
    if "skip_errors" not in body:
        raise ValueError("skip_errors is required")
    value = body["skip_errors"]
    if not isinstance(value, bool):
        raise ValueError("skip_errors must be a boolean")
    return value


def _parse_metadata_paths(
    body: dict[str, Any],
) -> tuple[Path | None, Path | None]:
    paths: list[Path | None] = []
    for key in ("filtered_metadata_path", "compressed_metadata_path"):
        raw_path = str(body.get(key) or "").strip()
        path = Path(raw_path).expanduser().resolve() if raw_path else None
        if path is not None and not path.is_file():
            raise ValueError(f"{key} does not exist: {path}")
        paths.append(path)
    return paths[0], paths[1]


def _validate_explicit_kind_disclosed_at_metadata(
    html_files: list[Path],
    metadata_index: dict[str, dict[str, Any]],
    filtered_metadata_path: Path | None,
) -> None:
    if filtered_metadata_path is None:
        return
    missing: list[str] = []
    invalid: list[str] = []
    for html_file in html_files:
        disclosed_at = str(
            (metadata_index.get(html_file.stem) or {}).get("disclosed_at") or ""
        ).strip()
        if not disclosed_at:
            missing.append(html_file.stem)
            continue
        try:
            parsed = datetime.strptime(disclosed_at, "%Y-%m-%d %H:%M")
        except ValueError:
            invalid.append(html_file.stem)
            continue
        if parsed.strftime("%Y-%m-%d %H:%M") != disclosed_at:
            invalid.append(html_file.stem)
    if missing:
        raise ValueError(
            "missing KIND disclosed_at metadata for HTML files: "
            + ", ".join(missing[:10])
        )
    if invalid:
        raise ValueError(
            "invalid KIND disclosed_at metadata for HTML files: "
            + ", ".join(invalid[:10])
        )


def _record_matches_filter_blocks(
    record: dict[str, Any], filter_blocks: list[dict[str, Any]]
) -> bool:
    if not filter_blocks:
        return True
    return _record_filter_blocks_match(record, filter_blocks)


def _require_payload_parser_method(payload: dict[str, Any]) -> str:
    parser_method = str(payload.get("parser_method") or "").strip()
    if not parser_method:
        raise ValueError("parser_method is required")
    return parser_method


def _derived_allowed_acpt_numbers(
    body: dict[str, Any],
    *,
    mode: str,
    filtered_metadata_path: Path | None,
) -> set[str] | None:
    if body.get("parent_mode") in (None, ""):
        return None
    if filtered_metadata_path is None:
        raise ValueError("filtered_metadata_path is required for a derived filter")
    filtered_payload, validated_filtered_path = _load_workspace_filtered_payload(
        {
            "data_root": body.get("data_root"),
            "mode": mode,
            "parent_mode": body.get("parent_mode"),
        }
    )
    if Path(validated_filtered_path) != filtered_metadata_path:
        raise ValueError(
            "derived filter filtered_metadata_path does not match its workspace path"
        )
    return set(collect_acpt_numbers_from_json(filtered_payload))


def _build_parse_request(
    body: dict[str, Any],
    cancel_check: Callable[[], bool] | None = None,
) -> ParseRequest:
    mode_value = str(body.get("mode") or "").strip()
    if not mode_value:
        raise ValueError("mode is required")
    mode = validate_workspace_mode(mode_value)
    parser_method = str(body.get("parser_method") or "").strip()
    if not parser_method:
        raise ValueError("parser_method is required")
    parser = PARSER_REGISTRY.get(parser_method)
    if parser is None:
        supported_methods = ", ".join(sorted(PARSER_REGISTRY))
        msg = (
            f"unsupported parser_method: {parser_method!r}. "
            f"supported methods: {supported_methods}"
        )
        raise ValueError(msg)
    parser_config = PARSER_METHOD_CONFIGS[parser_method]

    input_directory_raw = str(body.get("input_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    if not input_directory.is_dir():
        msg = f"input_directory does not exist: {input_directory}"
        raise ValueError(msg)

    output_directory_raw = str(body.get("output_directory") or "").strip()
    if not output_directory_raw:
        msg = "output_directory is required"
        raise ValueError(msg)
    output_directory = Path(output_directory_raw).expanduser().resolve()
    if output_directory.is_file():
        msg = "output_directory must be a directory path"
        raise ValueError(msg)
    output_path = output_directory / f"parsed-{mode}.json"
    limit = _parse_limit(body.get("limit"))
    cancel_token = str(body.get("cancel_token") or "").strip() or None

    filtered_metadata_path, compressed_metadata_path = _parse_metadata_paths(body)
    allowed_acpt_numbers = _derived_allowed_acpt_numbers(
        body,
        mode=mode,
        filtered_metadata_path=filtered_metadata_path,
    )
    html_files = _collect_html_files(
        input_directory,
        limit,
        allowed_acpt_numbers=allowed_acpt_numbers,
    )
    metadata_index, families = _load_html_parse_metadata(
        input_directory,
        filtered_metadata_path=filtered_metadata_path,
        compressed_metadata_path=compressed_metadata_path,
        allowed_acpt_numbers=allowed_acpt_numbers,
    )
    _validate_explicit_kind_disclosed_at_metadata(
        html_files,
        metadata_index,
        filtered_metadata_path,
    )

    return ParseRequest(
        mode=mode,
        parser_method=parser_method,
        parser=parser,
        reporting_company_field=parser_config.reporting_company_field,
        input_directory=input_directory,
        output_path=output_path,
        html_files=html_files,
        metadata_index=metadata_index,
        families=families,
        limit=limit,
        skip_errors=_parse_skip_errors(body),
        progress_interval=_parse_progress_interval(body.get("progress_interval")),
        parallel_workers=_parse_parallel_workers(
            body.get("parallel_workers"), len(html_files)
        ),
        cancel_token=cancel_token,
        cancel_check=cancel_check,
        filter_blocks=_parse_filter_blocks(body.get("filter_blocks")),
        record_filters=_parse_record_filters(body.get("record_filters")),
    )

WARNING_LEVEL_KEYS = ("weak_warning", "medium_warning", "strong_warning")
_BOND_INVESTOR_TABLE_MISSING_WARNING = (
    "사채 발행 투자자 표를 찾지 못했습니다. "
    "HTML 양식이 예상과 달라 투자자 필드가 비어 있을 수 있습니다."
)


def _build_warning_report_counts(warnings: list[dict[str, Any]]) -> dict[str, Any]:
    report_counts: dict[str, Any] = {
        "count": 0,
        "report_count": 0,
        "weak_warning": {"count": 0, "report_count": 0, "reports": {}},
        "medium_warning": {"count": 0, "report_count": 0, "reports": {}},
        "strong_warning": {"count": 0, "report_count": 0, "reports": {}},
    }
    report_numbers: set[str] = set()
    for warning in warnings:
        report_no = str(warning.get("acpt_no") or "")
        if not report_no:
            continue
        warning_message = str(warning.get("warning") or "").strip()
        if not warning_message:
            continue
        level = str(warning.get("level") or "").strip()
        if level not in WARNING_LEVEL_KEYS:
            msg = f"warning contract violation: unsupported level: {level!r}"
            raise ValueError(msg)
        report_numbers.add(report_no)
        report_counts["count"] += 1
        level_counts = report_counts[level]
        level_counts["count"] += 1
        report = level_counts["reports"].setdefault(
            report_no,
            {
                "count": 0,
                "warnings": [],
            },
        )
        report["count"] += 1
        report["warnings"].append(warning_message)
    report_counts["report_count"] = len(report_numbers)
    for level in WARNING_LEVEL_KEYS:
        report_counts[level]["report_count"] = len(report_counts[level]["reports"])
    return report_counts


def _build_payload(
    *,
    mode: str,
    parser_method: str,
    cancelled: bool,
    html_files: list[Path],
    records: list[dict[str, Any]],
    families: dict[str, dict[str, Any]],
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    filter_blocks: list[dict[str, Any]],
    record_filters: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "format": "finiq_disclosure_html_parse_v1",
        "mode": mode,
        "parser_method": parser_method,
        "cancelled": cancelled,
        "filter_settings": {
            "filter_blocks": filter_blocks,
            "record_filters": record_filters,
        },
        "warning_report_counts": _build_warning_report_counts(warnings),
        "summary": {
            "found_files": len(html_files),
            "parsed_files": len(records),
            "failed_files": len(errors),
        },
        "families": _saved_families(records, families),
        "records": records,
        "errors": errors,
        "warnings": warnings,
    }


def _write_parse_payload(payload: dict[str, Any], output_path: Path) -> None:
    atomic_write_json(output_path, payload)


def _payload_from_state(
    request: ParseRequest,
    state: ParseRunState,
    *,
    cancelled: bool,
) -> dict[str, Any]:
    return _build_payload(
        mode=request.mode,
        parser_method=request.parser_method,
        cancelled=cancelled,
        html_files=request.html_files,
        records=state.records,
        families=request.families,
        errors=state.errors,
        warnings=state.warnings,
        filter_blocks=request.filter_blocks,
        record_filters=request.record_filters,
    )


def _load_parse_payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        msg = f"parse result JSON does not exist: {path}"
        raise ValueError(msg)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"parse result JSON cannot be read: {path}"
        raise ValueError(msg) from exc
    if not isinstance(payload, dict):
        msg = "parse result JSON must contain an object"
        raise ValueError(msg)
    return payload


def _resolve_parse_result_path(output_directory: Path, mode: str) -> Path:
    if not str(mode or "").strip():
        raise ValueError("mode is required")
    mode = validate_workspace_mode(mode)
    if output_directory.is_file() or (
        not output_directory.exists() and output_directory.suffix
    ):
        msg = "output_path must be a directory path"
        raise ValueError(msg)
    return output_directory / f"parsed-{mode}.json"


def _record_without_raw_tables(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key != "raw_tables"
    }


def _saved_families(
    records: list[dict[str, Any]],
    family_registry: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    families: dict[str, Any] = {}
    for record in records:
        family_id = str(record.get("family_id") or "")
        if not family_id or family_id in families:
            continue
        family = family_registry.get(family_id)
        if not isinstance(family, dict):
            continue
        members = family.get("members")
        families[family_id] = {
            "members": members if isinstance(members, list) else [],
        }
    return families


def _record_parse_warning_items(record: dict[str, Any]) -> list[dict[str, str]]:
    unsupported_level_keys = sorted(
        key
        for key in record
        if isinstance(key, str)
        and key.endswith("_warning")
        and key not in WARNING_LEVEL_KEYS
    )
    if unsupported_level_keys:
        levels = ", ".join(unsupported_level_keys)
        msg = f"warning contract violation: unsupported warning levels: {levels}"
        raise ValueError(msg)

    parse_warnings = _record_warning_texts(record, "parse_warnings")

    level_by_warning: dict[str, str] = {}
    for key in WARNING_LEVEL_KEYS:
        for text in _record_warning_texts(record, key):
            if text in level_by_warning:
                msg = "warning contract violation: each warning must have one level"
                raise ValueError(msg)
            level_by_warning[text] = key

    if set(parse_warnings) != set(level_by_warning):
        msg = (
            "warning contract violation: parse_warnings and level lists must match"
        )
        raise ValueError(msg)

    return [
        {
            "warning": warning,
            "level": level_by_warning[warning],
            "warning_code": _warning_code(warning),
        }
        for warning in parse_warnings
    ]


def _record_warning_texts(record: dict[str, Any], key: str) -> list[str]:
    if key not in record:
        return []
    values = record[key]
    if not isinstance(values, list) or not values:
        msg = f"warning contract violation: {key} must be a non-empty list"
        raise ValueError(msg)
    if any(not isinstance(value, str) or not value.strip() for value in values):
        msg = f"warning contract violation: {key} must contain non-empty strings"
        raise ValueError(msg)
    if len(values) != len(set(values)):
        msg = f"warning contract violation: {key} must contain unique strings"
        raise ValueError(msg)
    return list(values)


def _warning_code(warning: str) -> str:
    if warning == _BOND_INVESTOR_TABLE_MISSING_WARNING:
        return "bond_investor_table_missing"
    if warning.startswith("발행목적: 자금조달 목적 합계"):
        return "bond_funding_purpose_sum_mismatch"
    if warning.startswith("투자자: 발행권면총액 합계"):
        return "bond_investor_sum_mismatch"
    if ": 정해진 출처에서 값을 찾지 못했습니다." in warning:
        field_name = warning.split(":", 1)[0].strip()
        return f"source_not_found:{field_name}" if field_name else "source_not_found"
    return "parse_warning"


def _record_parse_warnings(record: dict[str, Any]) -> list[str]:
    return [item["warning"] for item in _record_parse_warning_items(record)]


def _metadata_title_for_file(
    html_file: Path, metadata_index: dict[str, dict[str, Any]]
) -> str | None:
    acpt_no = html_file.stem
    metadata = metadata_index.get(acpt_no) or {}
    title = str(metadata.get("title") or "").strip()
    return title or None


def _metadata_company_name_for_file(
    html_file: Path, metadata_index: dict[str, dict[str, Any]]
) -> str | None:
    acpt_no = html_file.stem
    metadata = metadata_index.get(acpt_no) or {}
    company_name = str(metadata.get("company_name") or "").strip()
    return company_name or None


def _parser_accepts_title(parser: ParseFunction) -> bool:
    return "title" in signature(parser).parameters


def _parser_accepts_reporting_company_name(parser: ParseFunction) -> bool:
    return "reporting_company_name" in signature(parser).parameters


def _parse_html_file_record(request: ParseRequest, html_file: Path) -> dict[str, Any]:
    parser_kwargs: dict[str, Any] = {"file_path": html_file}
    title = _metadata_title_for_file(html_file, request.metadata_index)
    if title and _parser_accepts_title(request.parser):
        parser_kwargs["title"] = title
    company_name = _metadata_company_name_for_file(html_file, request.metadata_index)
    if company_name and _parser_accepts_reporting_company_name(request.parser):
        parser_kwargs["reporting_company_name"] = company_name
    return request.parser(html_file.read_bytes(), **parser_kwargs)


def _emit_run_header(request: ParseRequest, state: ParseRunState) -> None:
    state.emit(f"파싱 대상 HTML {len(request.html_files)}건을 찾았습니다.")
    state.emit(f"모드: {request.mode}")
    state.emit(f"파싱 방법: {request.parser_method}")
    if request.filter_blocks:
        state.emit(f"공시 조건: {len(request.filter_blocks)}개 조건 적용")
    if request.record_filters:
        state.emit(f"필드 필터: {len(request.record_filters)}개 조건 적용")
    state.emit(f"진행 확인 간격: {request.progress_interval}건")
    state.emit(f"병렬 처리: {request.parallel_workers}개 워커")


def _stringify_filter_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _record_matches_filter(record: dict[str, Any], record_filter: dict[str, Any]) -> bool:
    value = record.get(record_filter["field"])
    operator = record_filter["operator"]
    if operator == "exists":
        return value not in (None, "", [], {})
    actual = _stringify_filter_value(value)
    if operator == "in":
        expected_values = record_filter.get("value")
        if not isinstance(expected_values, list):
            return False
        return actual in {str(expected) for expected in expected_values}
    expected = record_filter["value"]
    if operator == "equals":
        return actual == expected
    return expected in actual


def _record_matches_filters(record: dict[str, Any], filters: list[dict[str, Any]]) -> bool:
    return all(_record_matches_filter(record, record_filter) for record_filter in filters)


def _add_parse_warning(
    request: ParseRequest,
    state: ParseRunState,
    *,
    index: int,
    html_file: Path,
    warning: str,
    level: str,
    warning_code: str,
) -> None:
    warning_info = {
        "index": index,
        "total": len(request.html_files),
        "mode": request.mode,
        "acpt_no": html_file.stem,
        "warning": warning,
        "level": level,
        "warning_code": warning_code,
    }
    state.warnings.append(warning_info)
    state.emit(
        f"파싱 경고 {index}/{len(request.html_files)}: {html_file.name} {warning}"
    )


def _add_parse_error(
    request: ParseRequest,
    state: ParseRunState,
    *,
    index: int,
    html_file: Path,
    exc: Exception,
) -> None:
    error_info = {
        "index": index,
        "total": len(request.html_files),
        "mode": request.mode,
        "acpt_no": html_file.stem,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }
    state.errors.append(error_info)
    state.emit(
        f"파싱 실패 {index}/{len(request.html_files)}: {html_file.name} "
        f"({error_info['error_type']}) {exc}"
    )


def _parse_one_html_file(
    request: ParseRequest,
    state: ParseRunState,
    *,
    index: int,
    html_file: Path,
) -> None:
    try:
        source_unavailable = _internal_html_source_unavailable_placeholder_file(
            html_file
        )
        parsed_record = (
            {
                "acpt_no": html_file.stem,
                "source_unavailable": {
                    "doc_no": source_unavailable["doc_no"],
                    "reason": source_unavailable["reason"],
                },
            }
            if source_unavailable is not None
            else _record_without_raw_tables(
                _parse_html_file_record(request, html_file)
            )
        )
        record = _apply_parse_metadata(
            parsed_record,
            request.metadata_index,
            reporting_company_field=request.reporting_company_field,
        )
        warning_items = _record_parse_warning_items(parsed_record)
        matches_filters = _record_matches_filters(
            record, request.record_filters
        ) and _record_matches_filter_blocks(record, request.filter_blocks)
        for warning_item in warning_items:
            _add_parse_warning(
                request,
                state,
                index=index,
                html_file=html_file,
                warning=warning_item["warning"],
                level=warning_item["level"],
                warning_code=warning_item["warning_code"],
            )
        if matches_filters:
            state.records.append(record)
    except Exception as exc:
        if not request.skip_errors:
            msg = (
                f"파싱 실패 {index}/{len(request.html_files)}: {html_file.name} "
                f"({type(exc).__name__}) {exc}"
            )
            raise ValueError(msg) from exc
        _add_parse_error(
            request,
            state,
            index=index,
            html_file=html_file,
            exc=exc,
        )

    state.processed_this_run += 1
    if (
        request.skip_errors
        and state.processed_this_run % request.progress_interval == 0
    ):
        _write_parse_payload(
            _payload_from_state(request, state, cancelled=False), request.output_path
        )
        state.emit(
            f"파싱 중간 확인: 이번 실행 {state.processed_this_run}건 처리, 결과 JSON 저장 완료."
        )


def _parse_html_file_for_worker(
    request: ParseRequest,
    *,
    index: int,
    html_file: Path,
) -> dict[str, Any]:
    try:
        source_unavailable = _internal_html_source_unavailable_placeholder_file(
            html_file
        )
        parsed_record = (
            {
                "acpt_no": html_file.stem,
                "source_unavailable": {
                    "doc_no": source_unavailable["doc_no"],
                    "reason": source_unavailable["reason"],
                },
            }
            if source_unavailable is not None
            else _record_without_raw_tables(
                _parse_html_file_record(request, html_file)
            )
        )
        record = _apply_parse_metadata(
            parsed_record,
            request.metadata_index,
            reporting_company_field=request.reporting_company_field,
        )
        warning_items = _record_parse_warning_items(parsed_record)
        matches_filters = _record_matches_filters(
            record, request.record_filters
        ) and _record_matches_filter_blocks(record, request.filter_blocks)
        return {
            "kind": "record",
            "index": index,
            "html_file": html_file,
            "record": record,
            "warnings": warning_items,
            "matches_filters": matches_filters,
        }
    except Exception as exc:
        return {
            "kind": "error",
            "index": index,
            "html_file": html_file,
            "error": exc,
        }


def _record_parallel_parse_result(
    request: ParseRequest,
    state: ParseRunState,
    result: dict[str, Any],
) -> None:
    index = int(result["index"])
    html_file = result["html_file"]
    if result["kind"] == "record":
        record = result["record"]
        for warning_item in result["warnings"]:
            _add_parse_warning(
                request,
                state,
                index=index,
                html_file=html_file,
                warning=warning_item["warning"],
                level=warning_item["level"],
                warning_code=warning_item["warning_code"],
            )
        if result["matches_filters"]:
            state.records.append(record)
    else:
        exc = result["error"]
        if not request.skip_errors:
            msg = (
                f"파싱 실패 {index}/{len(request.html_files)}: {html_file.name} "
                f"({type(exc).__name__}) {exc}"
            )
            raise ValueError(msg) from exc
        _add_parse_error(
            request,
            state,
            index=index,
            html_file=html_file,
            exc=exc,
        )

    state.processed_this_run += 1
    if (
        request.skip_errors
        and state.processed_this_run % request.progress_interval == 0
    ):
        _write_parse_payload(
            _payload_from_state(request, state, cancelled=False), request.output_path
        )
        state.emit(
            f"파싱 중간 확인: 이번 실행 {state.processed_this_run}건 처리, 결과 JSON 저장 완료."
        )


def _parse_html_files_parallel(request: ParseRequest, state: ParseRunState) -> None:
    pending_items = [
        (index, html_file)
        for index, html_file in enumerate(request.html_files, start=1)
    ]
    next_item = 0
    next_result_index = 0
    ready_results: dict[int, dict[str, Any]] = {}

    def submit_next(executor: ThreadPoolExecutor, futures: dict[Any, int]) -> None:
        nonlocal next_item
        if next_item >= len(pending_items) or _parse_cancelled(request):
            return
        index, html_file = pending_items[next_item]
        next_item += 1
        future = executor.submit(
            _parse_html_file_for_worker,
            request,
            index=index,
            html_file=html_file,
        )
        futures[future] = index

    with ThreadPoolExecutor(max_workers=request.parallel_workers) as executor:
        futures: dict[Any, int] = {}
        for _ in range(request.parallel_workers):
            submit_next(executor, futures)
        while futures:
            done, _pending = wait(futures, return_when=FIRST_COMPLETED)
            for future in done:
                futures.pop(future)
                result = future.result()
                ready_results[int(result["index"])] = result
                submit_next(executor, futures)

            while next_result_index < len(pending_items):
                expected_index = pending_items[next_result_index][0]
                result = ready_results.pop(expected_index, None)
                if result is None:
                    break
                _record_parallel_parse_result(request, state, result)
                next_result_index += 1
    if _parse_cancelled(request):
        state.emit(
            f"중지 요청으로 파싱을 멈췄습니다. "
            f"처리 완료 {len(state.records)}/{len(request.html_files)}건."
        )


def parse_disclosure_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Parse downloaded KIND section HTML files with the selected mode parser."""
    request = _build_parse_request(body, cancel_check=cancel_check)
    state = ParseRunState(progress_callback=progress_callback)
    _clear_cancel_token(request.cancel_token)
    _emit_run_header(request, state)

    try:
        if request.parallel_workers > 1:
            _parse_html_files_parallel(request, state)
        else:
            for index, html_file in enumerate(request.html_files, start=1):
                if _parse_cancelled(request):
                    state.emit(
                        f"중지 요청으로 파싱을 멈췄습니다. "
                        f"처리 완료 {len(state.records)}/{len(request.html_files)}건."
                    )
                    break
                _parse_one_html_file(request, state, index=index, html_file=html_file)
        cancelled = _parse_cancelled(request)
    finally:
        _clear_cancel_token(request.cancel_token)

    state.emit(f"파싱 결과 JSON 저장 중: {request.output_path}")
    payload = _payload_from_state(request, state, cancelled=cancelled)
    _write_parse_payload(payload, request.output_path)
    state.emit(f"파싱 결과 JSON 저장 완료: {request.output_path}")
    return payload


def inspect_disclosure_html_parse_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Recompute the current parse result and compare it with the saved JSON."""
    mode = str(body.get("mode") or "").strip()
    output_directory = Path(
        str(body.get("output_directory") or "").strip()
    ).expanduser().resolve()
    result_path = _resolve_parse_result_path(output_directory, mode)

    try:
        saved = _load_parse_payload(result_path)
        if saved.get("cancelled") is True or saved.get("errors"):
            raise ValueError("저장된 공시원문 변환 결과에 취소 또는 실패 기록이 있습니다.")
        with tempfile.TemporaryDirectory(prefix="finiq-parse-inspection-") as temporary:
            rebuilt = parse_disclosure_html_payload(
                {
                    **body,
                    "output_directory": temporary,
                    "cancel_token": "",
                }
            )
        if rebuilt != saved:
            raise ValueError("현재 설정과 입력 HTML로 다시 계산한 결과가 저장된 변환 결과와 다릅니다.")
    except Exception as error:
        return {
            "format": "finiq_disclosure_html_parse_inspection_v1",
            "confirmed": False,
            "reason": str(error),
            "result_path": str(result_path),
        }

    return {
        "format": "finiq_disclosure_html_parse_inspection_v1",
        "confirmed": True,
        "reason": "현재 설정으로 다시 변환한 내용이 저장된 결과와 모두 일치합니다.",
        "result_path": str(result_path),
        "summary": saved.get("summary") or {},
    }




__all__ = [name for name in globals() if not name.startswith("__")]
