"""KIND disclosure viewer HTML parsing helpers for the web UI."""

from __future__ import annotations

import json
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from inspect import signature
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from finiq.market_desk.web.features.market_data.service_common import (
    _record_filter_blocks_match,
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
class ParseModeConfig:
    """Mode metadata shared by parse, preview, filters, and UI-facing payloads."""

    key: str
    label: str
    status: str
    description: str
    parser: ParseFunction
    filters: tuple[ParseFilterConfig, ...] = ()


PARSE_MODE_CONFIGS = {
    "bond_issuance": ParseModeConfig(
        key="bond_issuance",
        label="사채발행파싱",
        status="상세 필드 지원",
        description="메자닌 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
        parser=parse_bond_issuance,
        filters=(ParseFilterConfig(field="사채발행방법", status_label="사채발행방법"),),
    ),
    "rights_issuance": ParseModeConfig(
        key="rights_issuance",
        label="유무상증자파싱",
        status="상세 필드 지원",
        description="유상증자 및 무상증자 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
        parser=parse_rights_issuance,
        filters=(ParseFilterConfig(field="증자방식", status_label="증자방식"),),
    ),
    "shareholder_meeting": ParseModeConfig(
        key="shareholder_meeting",
        label="주주총회파싱",
        status="원본 테이블 구조 지원",
        description="주주총회 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
        parser=parse_shareholder_meeting,
    ),
    "asset_transaction": ParseModeConfig(
        key="asset_transaction",
        label="유무형자산거래파싱",
        status="원본 테이블 구조 지원",
        description="유형자산 및 무형자산 거래 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
        parser=parse_asset_transaction,
    ),
    "security_transaction": ParseModeConfig(
        key="security_transaction",
        label="발행증권거래파싱",
        status="원본 테이블 구조 지원",
        description="발행증권 거래 공시 HTML에서 주요 필드와 엔티티를 추출합니다.",
        parser=parse_security_transaction,
    ),
}

PARSER_REGISTRY = {
    key: config.parser for key, config in PARSE_MODE_CONFIGS.items()
}


@dataclass(frozen=True)
class ParseRequest:
    """Validated options for one HTML parse run."""

    mode: str
    parser: ParseFunction
    input_directory: Path
    output_path: Path
    html_files: list[Path]
    metadata_index: dict[str, dict[str, Any]]
    limit: int | None
    skip_errors: bool
    progress_interval: int
    parallel_workers: int
    cancel_token: str | None
    filter_blocks: list[dict[str, Any]]
    record_filters: list[dict[str, Any]]


@dataclass
class ParseRunState:
    """Mutable parse run state that is eventually serialized as the result JSON."""

    progress_callback: ProgressCallback | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    progress_log: list[str] = field(default_factory=list)
    processed_this_run: int = 0

    def emit(self, message: str) -> None:
        self.progress_log.append(message)
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
    "source_file",
    "correction_families",
    "family_id",
    "current_sequence",
    "family_member_count",
    "raw_tables",
    "raw_rows",
    "index",
}
SOURCE_PREVIEW_MAX_TABLES = 12
SOURCE_PREVIEW_MAX_ROWS = 120


def _normalize_listing_market(value: Any) -> str:
    market = str(value or "").strip()
    if market == "유가증권":
        return "코스피"
    return market


def _load_html_parse_metadata_index(
    input_directory: Path,
) -> dict[str, dict[str, Any]]:
    metadata_index: dict[str, dict[str, Any]] = {}
    _merge_parse_metadata_from_directory(metadata_index, input_directory.parent)
    return metadata_index


def _merge_parse_metadata_from_directory(
    metadata_index: dict[str, dict[str, Any]],
    directory: Path,
) -> None:
    filtered_metadata_index: dict[str, dict[str, Any]] = {}
    compressed_metadata_index: dict[str, dict[str, Any]] = {}
    filtered_path = directory / "filtered.json"
    if filtered_path.is_file():
        filtered_metadata_index = _load_filtered_metadata_index(filtered_path)
    compressed_path = directory / "compressed-external-html.json"
    if compressed_path.is_file():
        compressed_metadata_index = _load_compressed_external_html_metadata_index(
            compressed_path
        )
    for acpt_no in sorted(set(filtered_metadata_index) | set(compressed_metadata_index)):
        metadata: dict[str, Any] = {}
        metadata.update(filtered_metadata_index.get(acpt_no, {}))
        metadata.update(compressed_metadata_index.get(acpt_no, {}))
        metadata_index[acpt_no] = metadata


def _filtered_metadata_item(item: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    acpt_no = str(item.get("acpt_no") or "").strip()
    if not acpt_no:
        return None
    return acpt_no, {
        "market": _normalize_listing_market(item.get("market")),
        "company_name": str(item.get("company_name") or "").strip(),
    }


def _compressed_external_html_metadata_item(
    item: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    acpt_no = str(item.get("acpt_no") or "").strip()
    if not acpt_no:
        return None
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
    if not isinstance(payload, dict):
        return {}
    metadata_index: dict[str, dict[str, Any]] = {}
    disclosures = [
        item for item in payload.get("disclosures") or [] if isinstance(item, dict)
    ]
    for item in disclosures:
        if not isinstance(item, dict):
            continue
        parsed = _filtered_metadata_item(item)
        if parsed is not None:
            acpt_no, metadata = parsed
            metadata_index[acpt_no] = metadata
    return metadata_index


def _load_compressed_external_html_metadata_index(
    compressed_path: Path,
) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(compressed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"외부 HTML 압축 JSON을 읽을 수 없습니다: {compressed_path}"
        ) from exc
    if not isinstance(payload, dict):
        return {}
    records = [item for item in payload.get("records") or [] if isinstance(item, dict)]
    selected_doc_to_record = {
        str(item.get("selected_main_doc_no") or "").strip(): item
        for item in records
        if str(item.get("selected_main_doc_no") or "").strip()
    }
    metadata_index: dict[str, dict[str, Any]] = {}
    for item in records:
        if not isinstance(item, dict):
            continue
        parsed = _compressed_external_html_metadata_item(item)
        if parsed is not None:
            acpt_no, metadata = parsed
            family = _external_html_correction_family(item, selected_doc_to_record)
            if family:
                metadata["correction_families"] = family
            metadata_index[acpt_no] = metadata
    return metadata_index


def _external_html_correction_family(
    item: dict[str, Any],
    selected_doc_to_record: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
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
        metadata = member_record.get("metadata") or {}
        title = str(doc.get("text") or "").strip()
        members.append(
            {
                "sequence": sequence,
                "acpt_no": str(member_record.get("acpt_no") or "").strip(),
                "doc_no": doc_no,
                "title": title,
                "disclosed_at": str(metadata.get("disclosed_at") or "").strip(),
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
    family_id = str(members[-1].get("acpt_no") or "").strip()
    if current_sequence is None or not family_id:
        return None
    return {
        family_id: {
            "current_sequence": current_sequence,
            "members": members,
        }
    }


def _external_main_doc_sort_key(doc: dict[str, Any]) -> tuple[int, str]:
    try:
        option_index = int(doc.get("option_index"))
    except (TypeError, ValueError):
        option_index = 0
    return (option_index, str(doc.get("doc_no") or ""))


def _external_doc_is_correction(doc: dict[str, Any], title: str) -> bool:
    text = str(doc.get("text") or "")
    return "정정" in text or "정정" in title


def _apply_parse_metadata(
    record: dict[str, Any],
    metadata_index: dict[str, dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    acpt_no = str(record.get("acpt_no") or "").strip()
    metadata = metadata_index.get(acpt_no) or {}
    market = metadata.get("market")
    company_name = metadata.get("company_name")
    doc_no = metadata.get("doc_no")
    correction_families = metadata.get("correction_families")
    if (
        not market
        and not company_name
        and not doc_no
        and not correction_families
    ):
        return record
    updated_record = dict(record)
    if doc_no and not updated_record.get("doc_no"):
        updated_record["doc_no"] = doc_no
    if correction_families:
        updated_record["correction_families"] = correction_families
    if market:
        updated_record["상장구분"] = market
    if mode in {"bond_issuance", "rights_issuance"} and company_name:
        updated_record["corp_name"] = company_name
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
    if value in (None, ""):
        return 1
    try:
        requested_workers = int(value)
    except (TypeError, ValueError):
        requested_workers = 1
    return max(1, min(requested_workers, max(1, total_files)))


def _collect_html_files(input_directory: Path, limit: int | None) -> list[Path]:
    files = sorted(path for path in input_directory.rglob("*.html") if path.is_file())
    return files[:limit] if limit is not None else files


def _parse_record_filters(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    filters: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "").strip()
        if not field:
            continue
        operator = str(item.get("operator") or "contains").strip()
        if operator not in SUPPORTED_RECORD_FILTER_OPERATORS:
            operator = "contains"
        raw_value = item.get("value")
        if operator == "in":
            values = [
                str(candidate).strip()
                for candidate in raw_value
                if str(candidate).strip()
            ] if isinstance(raw_value, list) else []
            if not values:
                continue
            filters.append({"field": field, "operator": operator, "value": values})
            continue
        filter_value = str(raw_value or "").strip()
        if operator != "exists" and not filter_value:
            continue
        filters.append({"field": field, "operator": operator, "value": filter_value})
    return filters


def _parse_filter_blocks(value: Any) -> list[dict[str, Any]]:
    return value if isinstance(value, list) else []


def _record_matches_filter_blocks(
    record: dict[str, Any], filter_blocks: list[dict[str, Any]]
) -> bool:
    if not filter_blocks:
        return True
    return _record_filter_blocks_match(record, filter_blocks)


def _build_parse_request(body: dict[str, Any]) -> ParseRequest:
    mode = str(body.get("mode") or "").strip()
    if not mode:
        msg = "mode is required"
        raise ValueError(msg)
    parser = PARSER_REGISTRY.get(mode)
    if parser is None:
        supported_modes = ", ".join(sorted(PARSER_REGISTRY))
        msg = f"unsupported mode: {mode!r}. supported modes: {supported_modes}"
        raise ValueError(msg)

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

    html_files = _collect_html_files(input_directory, limit)

    return ParseRequest(
        mode=mode,
        parser=parser,
        input_directory=input_directory,
        output_path=output_path,
        html_files=html_files,
        metadata_index=_load_html_parse_metadata_index(input_directory),
        limit=limit,
        skip_errors=bool(body.get("skip_errors", True)),
        progress_interval=_parse_progress_interval(body.get("progress_interval")),
        parallel_workers=_parse_parallel_workers(
            body.get("parallel_workers", body.get("workers")), len(html_files)
        ),
        cancel_token=cancel_token,
        filter_blocks=_parse_filter_blocks(body.get("filter_blocks")),
        record_filters=_parse_record_filters(body.get("record_filters")),
    )

WARNING_LEVEL_KEYS = ("weak_warning", "medium_warning", "strong_warning")
_BOND_MAIN_TABLE_MISSING_WARNING = (
    "사채 발행 주요 표를 찾지 못했습니다. HTML 양식이 예상과 달라 일부 필드가 비어 있을 수 있습니다."
)
_RIGHTS_ISSUE_TYPE_MISSING_WARNING = (
    "주입 제목에서 유상증자/무상증자 유형을 확인하지 못했습니다. 일부 필드가 비어 있을 수 있습니다."
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
        source_name = str(warning.get("source_name") or "").strip()
        report_no = Path(source_name).stem if source_name else ""
        if not report_no:
            continue
        warning_message = str(warning.get("warning") or "").strip()
        if not warning_message:
            continue
        level = str(warning.get("level") or "medium_warning").strip()
        if level not in WARNING_LEVEL_KEYS:
            level = "medium_warning"
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
    cancelled: bool,
    html_files: list[Path],
    records: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    filter_blocks: list[dict[str, Any]],
    record_filters: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "format": "finiq_disclosure_html_parse_v1",
        "mode": mode,
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
        "families": _saved_correction_families(records),
        "records": _saved_records(records),
        "errors": errors,
        "warnings": warnings,
    }


def _write_parse_payload(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _payload_from_state(
    request: ParseRequest,
    state: ParseRunState,
    *,
    cancelled: bool,
) -> dict[str, Any]:
    return _build_payload(
        mode=request.mode,
        cancelled=cancelled,
        html_files=request.html_files,
        records=state.records,
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
    if not mode:
        msg = "mode is required"
        raise ValueError(msg)
    if mode not in PARSER_REGISTRY:
        supported_modes = ", ".join(sorted(PARSER_REGISTRY))
        msg = f"unsupported mode: {mode!r}. supported modes: {supported_modes}"
        raise ValueError(msg)
    if output_directory.is_file() or (
        not output_directory.exists() and output_directory.suffix
    ):
        msg = "output_path must be a directory path"
        raise ValueError(msg)
    return output_directory / f"parsed-{mode}.json"


def _compact_record(record: dict[str, Any]) -> dict[str, Any]:
    def compact_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: compact_value(nested_value)
                for key, nested_value in value.items()
                if key != "rcept_no"
            }
        if isinstance(value, list):
            return [compact_value(item) for item in value]
        return value

    return {
        key: compact_value(value)
        for key, value in record.items()
        if key not in {"raw_tables", "raw_rows", "rcept_no"}
    }


def _record_correction_family_info(
    record: dict[str, Any],
) -> tuple[str, int | None, int | None]:
    families = record.get("correction_families")
    if not isinstance(families, dict) or not families:
        return ("", None, None)
    family_id = str(next(iter(families)))
    family = families.get(family_id)
    if not isinstance(family, dict):
        return (family_id, None, None)
    current_sequence_raw = family.get("current_sequence")
    current_sequence = (
        current_sequence_raw if isinstance(current_sequence_raw, int) else None
    )
    members = family.get("members")
    member_count = len(members) if isinstance(members, list) else None
    return (family_id, current_sequence, member_count)


def _saved_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    saved_records: list[dict[str, Any]] = []
    for record in records:
        saved_record = {
            key: value
            for key, value in record.items()
            if key not in {"source_file", "correction_families"}
        }
        family_id, current_sequence, member_count = _record_correction_family_info(
            record
        )
        if family_id:
            saved_record["family_id"] = family_id
            saved_record["current_sequence"] = current_sequence
            saved_record["family_member_count"] = member_count
        saved_records.append(saved_record)
    return saved_records


def _saved_correction_families(records: list[dict[str, Any]]) -> dict[str, Any]:
    families: dict[str, Any] = {}
    for record in records:
        record_families = record.get("correction_families")
        if not isinstance(record_families, dict):
            continue
        for family_key, family in record_families.items():
            family_id = str(family_key)
            if (
                not family_id
                or family_id in families
                or not isinstance(family, dict)
            ):
                continue
            members = family.get("members")
            families[family_id] = {
                "members": members if isinstance(members, list) else [],
            }
    return families


def _build_preview_record(
    record: dict[str, Any], *, index: int, mode: str
) -> dict[str, Any]:
    compact_record = _compact_record(record)
    compact_record.pop("correction_families", None)
    return {
        "index": index,
        "title": record.get("title") or "",
        "acpt_no": record.get("acpt_no") or "",
        "source_file": record.get("source_file") or "",
        "source_preview": _load_source_preview(record, mode=mode),
        "parsed_result": compact_record,
    }


def _record_parse_warning_items(record: dict[str, Any]) -> list[dict[str, str]]:
    level_by_warning: dict[str, str] = {}
    for key in WARNING_LEVEL_KEYS:
        warnings = record.get(key)
        if not isinstance(warnings, list):
            continue
        for warning in warnings:
            text = str(warning).strip()
            if text and text not in level_by_warning:
                level_by_warning[text] = key

    collected: list[dict[str, str]] = []
    seen: set[str] = set()
    for key in ("parse_warnings", *WARNING_LEVEL_KEYS):
        warnings = record.get(key)
        if not isinstance(warnings, list):
            continue
        for warning in warnings:
            text = str(warning).strip()
            if text and text not in seen:
                seen.add(text)
                collected.append(
                    {
                        "warning": text,
                        "level": level_by_warning.get(text, "medium_warning"),
                        "warning_code": _warning_code(text),
                    }
                )
    return collected


def _warning_code(warning: str) -> str:
    if warning == _BOND_MAIN_TABLE_MISSING_WARNING:
        return "bond_main_table_missing"
    if warning == _RIGHTS_ISSUE_TYPE_MISSING_WARNING:
        return "rights_issue_type_missing"
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
    acpt_no = html_file.stem.split("_", 1)[0]
    metadata = metadata_index.get(acpt_no) or {}
    title = str(metadata.get("title") or "").strip()
    return title or None


def _parser_accepts_title(parser: ParseFunction) -> bool:
    try:
        return "title" in signature(parser).parameters
    except (TypeError, ValueError):
        return False


def _parse_html_file_record(request: ParseRequest, html_file: Path) -> dict[str, Any]:
    parser_kwargs: dict[str, Any] = {"file_path": html_file}
    title = _metadata_title_for_file(html_file, request.metadata_index)
    if title and _parser_accepts_title(request.parser):
        parser_kwargs["title"] = title
    return request.parser(html_file.read_bytes(), **parser_kwargs)


def _emit_run_header(request: ParseRequest, state: ParseRunState) -> None:
    state.emit(f"파싱 대상 HTML {len(request.html_files)}건을 찾았습니다.")
    state.emit(f"파싱 모드: {request.mode}")
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
    source_file: str,
    warning: str,
    level: str,
    warning_code: str,
) -> None:
    warning_info = {
        "index": index,
        "total": len(request.html_files),
        "mode": request.mode,
        "source_file": source_file,
        "source_name": html_file.name,
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
    source_file: str,
    exc: Exception,
) -> None:
    error_info = {
        "index": index,
        "total": len(request.html_files),
        "mode": request.mode,
        "source_file": source_file,
        "source_name": html_file.name,
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
    source_file = str(html_file.resolve())
    try:
        parsed_record = _compact_record(
            _parse_html_file_record(request, html_file)
        )
        record = _apply_parse_metadata(
            parsed_record,
            request.metadata_index,
            mode=request.mode,
        )
        if _record_matches_filters(
            record, request.record_filters
        ) and _record_matches_filter_blocks(record, request.filter_blocks):
            for warning_item in _record_parse_warning_items(parsed_record):
                _add_parse_warning(
                    request,
                    state,
                    index=index,
                    html_file=html_file,
                    source_file=source_file,
                    warning=warning_item["warning"],
                    level=warning_item["level"],
                    warning_code=warning_item["warning_code"],
                )
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
            source_file=source_file,
            exc=exc,
        )

    state.processed_this_run += 1
    if state.processed_this_run % request.progress_interval == 0:
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
    source_file = str(html_file.resolve())
    try:
        parsed_record = _compact_record(
            _parse_html_file_record(request, html_file)
        )
        return {
            "kind": "record",
            "index": index,
            "html_file": html_file,
            "source_file": source_file,
            "record": _apply_parse_metadata(
                parsed_record,
                request.metadata_index,
                mode=request.mode,
            ),
            "warnings": _record_parse_warning_items(parsed_record),
        }
    except Exception as exc:
        return {
            "kind": "error",
            "index": index,
            "html_file": html_file,
            "source_file": source_file,
            "error": exc,
        }


def _record_parallel_parse_result(
    request: ParseRequest,
    state: ParseRunState,
    result: dict[str, Any],
) -> None:
    index = int(result["index"])
    html_file = result["html_file"]
    source_file = str(result["source_file"])
    if result["kind"] == "record":
        record = result["record"]
        if _record_matches_filters(record, request.record_filters) and _record_matches_filter_blocks(record, request.filter_blocks):
            for warning_item in result["warnings"]:
                _add_parse_warning(
                    request,
                    state,
                    index=index,
                    html_file=html_file,
                    source_file=source_file,
                    warning=warning_item["warning"],
                    level=warning_item["level"],
                    warning_code=warning_item["warning_code"],
                )
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
            source_file=source_file,
            exc=exc,
        )

    state.processed_this_run += 1
    if state.processed_this_run % request.progress_interval == 0:
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
        if next_item >= len(pending_items) or _is_cancelled(request.cancel_token):
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
    if _is_cancelled(request.cancel_token):
        state.emit(
            f"중지 요청으로 파싱을 멈췄습니다. "
            f"처리 완료 {len(state.records)}/{len(request.html_files)}건."
        )


def parse_disclosure_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Parse downloaded KIND viewer HTML files with the selected mode parser."""
    request = _build_parse_request(body)
    state = ParseRunState(progress_callback=progress_callback)
    _clear_cancel_token(request.cancel_token)
    _emit_run_header(request, state)

    try:
        if request.parallel_workers > 1:
            _parse_html_files_parallel(request, state)
        else:
            for index, html_file in enumerate(request.html_files, start=1):
                if _is_cancelled(request.cancel_token):
                    state.emit(
                        f"중지 요청으로 파싱을 멈췄습니다. "
                        f"처리 완료 {len(state.records)}/{len(request.html_files)}건."
                    )
                    break
                _parse_one_html_file(request, state, index=index, html_file=html_file)
        cancelled = _is_cancelled(request.cancel_token)
    finally:
        _clear_cancel_token(request.cancel_token)

    state.emit(f"파싱 결과 JSON 저장 중: {request.output_path}")
    state.emit(f"파싱 결과 JSON 저장 완료: {request.output_path}")

    payload = _payload_from_state(request, state, cancelled=cancelled)
    _write_parse_payload(payload, request.output_path)
    return payload




__all__ = [name for name in globals() if not name.startswith("__")]
