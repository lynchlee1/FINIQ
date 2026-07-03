"""KIND disclosure viewer HTML parsing helpers for the web UI."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from finiq.market_desk.web.features.disclosures.html_common import HTML_MANIFEST_FILENAME
from finiq.market_desk.web.html_parsers import (
    parse_asset_transaction,
    parse_bond_issuance,
    parse_rights_issuance,
    parse_security_transaction,
    parse_shareholder_meeting,
)
from finiq.market_desk.web.html_parsers.common import (
    build_base_record,
    fetch_selected_viewer_body,
)

ParseFunction = Callable[[str | bytes], dict[str, Any]]
ProgressCallback = Callable[[str], None]
_CANCELLED_PARSES: set[str] = set()
_CANCEL_LOCK = Lock()
_PARSE_CACHE: dict[str, dict[str, Any]] = {}
_CACHE_LOCK = Lock()

PARSER_REGISTRY = {
    "bond_issuance": parse_bond_issuance,
    "rights_issuance": parse_rights_issuance,
    "shareholder_meeting": parse_shareholder_meeting,
    "asset_transaction": parse_asset_transaction,
    "security_transaction": parse_security_transaction,
}


@dataclass(frozen=True)
class ParseRequest:
    """Validated options for one HTML parse run."""

    mode: str
    parser: ParseFunction
    input_directory: Path
    output_path: Path
    html_files: list[Path]
    manifest_metadata_index: dict[str, dict[str, Any]]
    limit: int | None
    skip_errors: bool
    resume: bool
    progress_interval: int
    cancel_token: str | None


@dataclass
class ParseRunState:
    """Mutable parse run state that is eventually serialized as the result JSON."""

    progress_callback: ProgressCallback | None = None
    records: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    progress_log: list[str] = field(default_factory=list)
    processed_files: set[str] = field(default_factory=set)
    resumed_files: int = 0
    processed_this_run: int = 0
    skipped_resume_count: int = 0

    def emit(self, message: str) -> None:
        self.progress_log.append(message)
        if self.progress_callback is not None:
            self.progress_callback(message)


BOND_SUMMARY_FIELDS = (
    "기업명(발행사)",
    "회차",
    "종류",
    "기업명(행사대상)",
    "상장구분",
    "발행금액",
    "행사가액",
    "납입일",
    "만기일",
    "행사시작일",
    "행사종료일",
    "투자자",
)
CHANGE_LOG_FIELDS = {
    "bond_issuance": (
        "기업명(발행사)",
        "회차",
        "종류",
        "기업명(행사대상)",
        "상장구분",
        "발행금액",
        "행사가액",
        "납입일",
        "만기일",
        "행사시작일",
        "행사종료일",
        "투자자",
    ),
    "rights_issuance": (
        "상장시장",
        "신주의 종류와 수",
        "발행목적",
        "발행가액",
        "기준주가",
        "증자방식",
        "납입일",
        "신주권교부예정일",
        "상장예정일",
        "발행대상자",
        "발행대상자세부엔티티",
    ),
}
MAJOR_CHANGE_FIELDS = {
    "bond_issuance": {
        "기업명(발행사)",
        "종류",
        "기업명(행사대상)",
        "상장구분",
        "발행금액",
        "행사가액",
        "납입일",
        "만기일",
        "행사시작일",
        "행사종료일",
        "투자자",
    },
    "rights_issuance": {
        "신주의 종류와 수",
        "발행목적",
        "발행가액",
        "기준주가",
        "증자방식",
        "납입일",
        "신주권교부예정일",
        "상장예정일",
        "발행대상자",
        "발행대상자세부엔티티",
    },
}

# Fields that should always be excluded from change detection as they are metadata
METADATA_FIELDS = {
    "title",
    "acpt_no",
    "rcept_no",
    "source_file",
    "correction_families",
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


def _load_html_manifest_metadata_index(
    input_directory: Path,
) -> dict[str, dict[str, Any]]:
    metadata_index: dict[str, dict[str, Any]] = {}
    manifest_path = input_directory / HTML_MANIFEST_FILENAME
    if manifest_path.is_file():
        _merge_metadata_index(
            metadata_index, _load_download_manifest_metadata_index(manifest_path)
        )
    for directory in (
        input_directory,
        input_directory.parent,
        input_directory.parent.parent,
    ):
        filtered_path = directory / "filtered.json"
        if filtered_path.is_file():
            _merge_metadata_index(
                metadata_index, _load_filtered_metadata_index(filtered_path)
            )
        compressed_path = directory / "compressed-external-html.json"
        if compressed_path.is_file():
            _merge_metadata_index(
                metadata_index,
                _load_compressed_external_html_metadata_index(compressed_path),
            )
    return metadata_index


def _merge_metadata_index(
    target: dict[str, dict[str, Any]], source: dict[str, dict[str, Any]]
) -> None:
    for acpt_no, metadata in source.items():
        current = target.setdefault(acpt_no, {})
        for key, value in metadata.items():
            if value:
                if key in {"rcept_no", "correction_families"} and current.get(key):
                    continue
                current[key] = value


def _load_download_manifest_metadata_index(
    manifest_path: Path,
) -> dict[str, dict[str, Any]]:
    if not manifest_path.is_file():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"HTML 메타데이터 manifest를 읽을 수 없습니다: {manifest_path}"
        ) from exc
    if not isinstance(payload, dict):
        return {}
    metadata_index: dict[str, dict[str, Any]] = {}
    for item in payload.get("disclosures") or []:
        if not isinstance(item, dict):
            continue
        acpt_no = str(item.get("acpt_no") or "").strip()
        market = _normalize_listing_market(item.get("market"))
        company_name = str(item.get("company_name") or "").strip()
        if acpt_no:
            metadata_index[acpt_no] = {
                "market": market,
                "company_name": company_name,
            }
    return metadata_index


def _metadata_item(item: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    acpt_no = str(item.get("acpt_no") or "").strip()
    if not acpt_no:
        return None
    selected_main_doc_no = str(item.get("selected_main_doc_no") or "").strip()
    doc_no = str(item.get("doc_no") or selected_main_doc_no or "").strip()
    metadata = {
        "market": _normalize_listing_market(item.get("market")),
        "company_name": str(item.get("company_name") or "").strip(),
        "title": str(
            item.get("title")
            or item.get("title_display")
            or item.get("title_attr")
            or ""
        ).strip(),
        "doc_no": doc_no,
        "selected_main_doc_no": selected_main_doc_no,
    }
    docs = item.get("docs")
    if isinstance(docs, list):
        metadata["docs"] = [doc for doc in docs if isinstance(doc, dict)]
    header = str(item.get("header") or "").strip()
    if header and not metadata["company_name"]:
        metadata["company_name"] = re.sub(r"\s*\([^)]*\)\s*$", "", header).strip()
    return acpt_no, metadata


def _filtered_correction_group_key(item: dict[str, Any]) -> tuple[str, str]:
    company_key = str(item.get("company_key") or item.get("company_name") or "").strip()
    title_base = str(
        item.get("title_base") or item.get("title_attr") or item.get("title") or ""
    ).strip()
    return (company_key, title_base)


def _filtered_disclosed_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    disclosed_at = str(item.get("disclosed_at") or "").strip()
    try:
        disclosed_key = datetime.strptime(disclosed_at, "%Y-%m-%d %H:%M").isoformat()
    except ValueError:
        disclosed_key = disclosed_at
    return (disclosed_key, str(item.get("acpt_no") or ""))


def _apply_filtered_correction_metadata(
    metadata_index: dict[str, dict[str, Any]], rows: list[dict[str, Any]]
) -> None:
    unique_rows = {
        str(row.get("acpt_no") or "").strip(): row
        for row in rows
        if str(row.get("acpt_no") or "").strip()
    }
    rows_by_group: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in unique_rows.values():
        key = _filtered_correction_group_key(row)
        if key[0] and key[1]:
            rows_by_group.setdefault(key, []).append(row)

    for group_rows in rows_by_group.values():
        current_family: list[dict[str, Any]] = []
        for row in sorted(group_rows, key=_filtered_disclosed_sort_key):
            is_correction = bool(row.get("is_correction_report"))
            if not is_correction:
                if len(current_family) > 1:
                    _store_filtered_correction_family(metadata_index, current_family)
                current_family = [row]
            elif current_family:
                current_family.append(row)
            else:
                current_family = [row]
        if len(current_family) > 1:
            _store_filtered_correction_family(metadata_index, current_family)


def _store_filtered_correction_family(
    metadata_index: dict[str, dict[str, Any]],
    family_rows: list[dict[str, Any]],
) -> None:
    family_id = str(family_rows[-1].get("acpt_no") or "").strip()
    if not family_id:
        return
    members = []
    for sequence, row in enumerate(family_rows):
        acpt_no = str(row.get("acpt_no") or "").strip()
        doc_no = str(row.get("doc_no") or "").strip() or None
        members.append(
            {
                "sequence": sequence,
                "acpt_no": acpt_no,
                "doc_no": doc_no,
                "title": row.get("title_display") or row.get("title") or "",
                "disclosed_at": row.get("disclosed_at") or "",
                "is_correction_report": bool(row.get("is_correction_report")),
            }
        )
    for current_sequence, row in enumerate(family_rows):
        acpt_no = str(row.get("acpt_no") or "").strip()
        if not acpt_no:
            continue
        metadata = metadata_index.setdefault(acpt_no, {})
        metadata["correction_families"] = {
            family_id: {
                "current_sequence": current_sequence,
                "members": members,
            }
        }


def _load_filtered_metadata_index(filtered_path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(filtered_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"필터 결과 JSON을 읽을 수 없습니다: {filtered_path}") from exc
    if not isinstance(payload, dict):
        return {}
    metadata_index: dict[str, dict[str, Any]] = {}
    rows = [
        item
        for item in [*(payload.get("rows") or []), *(payload.get("disclosures") or [])]
        if isinstance(item, dict)
    ]
    for item in rows:
        if not isinstance(item, dict):
            continue
        parsed = _metadata_item(item)
        if parsed is not None:
            acpt_no, metadata = parsed
            metadata_index[acpt_no] = metadata
    _apply_filtered_correction_metadata(metadata_index, rows)
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
    metadata_index: dict[str, dict[str, Any]] = {}
    for item in payload.get("records") or []:
        if not isinstance(item, dict):
            continue
        parsed = _metadata_item(item)
        if parsed is not None:
            acpt_no, metadata = parsed
            metadata_index[acpt_no] = metadata
    return metadata_index


def _apply_manifest_metadata(
    record: dict[str, Any],
    metadata_index: dict[str, dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    acpt_no = str(record.get("acpt_no") or "").strip()
    metadata = metadata_index.get(acpt_no) or {}
    market = metadata.get("market")
    company_name = metadata.get("company_name")
    title = metadata.get("title")
    rcept_no = metadata.get("rcept_no")
    doc_no = metadata.get("doc_no")
    selected_main_doc_no = metadata.get("selected_main_doc_no")
    docs = metadata.get("docs")
    correction_families = metadata.get("correction_families")
    if (
        not market
        and not company_name
        and not title
        and not rcept_no
        and not doc_no
        and not selected_main_doc_no
        and not docs
        and not correction_families
    ):
        return record
    updated_record = dict(record)
    if title and not updated_record.get("title"):
        updated_record["title"] = title
    if rcept_no and not updated_record.get("rcept_no"):
        updated_record["rcept_no"] = rcept_no
    if doc_no and not updated_record.get("doc_no"):
        updated_record["doc_no"] = doc_no
    if selected_main_doc_no and not updated_record.get("selected_main_doc_no"):
        updated_record["selected_main_doc_no"] = selected_main_doc_no
    if docs and not updated_record.get("docs"):
        updated_record["docs"] = docs
    if correction_families:
        updated_record["correction_families"] = correction_families
    if mode == "bond_issuance":
        if market:
            updated_record["상장구분"] = market
        if company_name:
            updated_record["기업명(발행사)"] = company_name
    elif market:
        updated_record["상장시장"] = market
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
        return 10
    parsed = int(value)
    if parsed < 1:
        msg = "progress_interval must be >= 1"
        raise ValueError(msg)
    return parsed


def _collect_html_files(input_directory: Path, limit: int | None) -> list[Path]:
    files = sorted(path for path in input_directory.rglob("*.html") if path.is_file())
    return files[:limit] if limit is not None else files


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

    output_path_raw = str(body.get("output_path") or "").strip()
    output_path = (
        Path(output_path_raw).expanduser().resolve()
        if output_path_raw
        else input_directory / f"parsed-{mode}.json"
    )
    limit = _parse_limit(body.get("limit"))
    cancel_token = str(body.get("cancel_token") or "").strip() or None

    return ParseRequest(
        mode=mode,
        parser=parser,
        input_directory=input_directory,
        output_path=output_path,
        html_files=_collect_html_files(input_directory, limit),
        manifest_metadata_index=_load_html_manifest_metadata_index(input_directory),
        limit=limit,
        skip_errors=bool(body.get("skip_errors", True)),
        resume=bool(body.get("resume", True)),
        progress_interval=_parse_progress_interval(body.get("progress_interval")),
        cancel_token=cancel_token,
    )


def _load_existing_parse_payload(output_path: Path, mode: str) -> dict[str, Any] | None:
    if not output_path.is_file():
        return None
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"기존 파싱 결과 JSON을 읽을 수 없습니다: {output_path}"
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("format") != "finiq_disclosure_html_parse_v1"
    ):
        return None
    if payload.get("mode") != mode:
        return None
    return payload


def _processed_source_files(
    records: list[dict[str, Any]], errors: list[dict[str, Any]]
) -> set[str]:
    processed: set[str] = set()
    for item in [*records, *errors]:
        source_file = str(item.get("source_file") or "").strip()
        if source_file:
            processed.add(str(Path(source_file).expanduser().resolve()))
    return processed


def _rcept_no_to_acpt_no(records: list[dict[str, Any]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for record in records:
        rcept_no = str(record.get("rcept_no") or "").strip()
        acpt_no = str(record.get("acpt_no") or "").strip()
        if rcept_no and acpt_no:
            index.setdefault(rcept_no, acpt_no)
    return index


def _resolve_correction_family_acpt_numbers(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rcept_to_acpt = _rcept_no_to_acpt_no(records)
    resolved_records: list[dict[str, Any]] = []
    for record in records:
        resolved_record = dict(record)
        families = record.get("correction_families")
        if not isinstance(families, dict):
            resolved_records.append(resolved_record)
            continue

        resolved_families: dict[str, Any] = {}
        for family_id, family in families.items():
            if not isinstance(family, dict):
                resolved_families[str(family_id)] = family
                continue
            resolved_family = dict(family)
            members = family.get("members")
            if isinstance(members, list):
                resolved_members = []
                for member in members:
                    if not isinstance(member, dict):
                        resolved_members.append(member)
                        continue
                    resolved_member = dict(member)
                    rcept_no = str(resolved_member.get("rcept_no") or "").strip()
                    if rcept_no and not resolved_member.get("acpt_no"):
                        resolved_member["acpt_no"] = rcept_to_acpt.get(rcept_no)
                    resolved_members.append(resolved_member)
                resolved_family["members"] = resolved_members
            resolved_families[str(family_id)] = resolved_family
        resolved_record["correction_families"] = resolved_families
        resolved_records.append(resolved_record)
    return resolved_records


def _build_payload(
    *,
    mode: str,
    input_directory: Path,
    output_path: Path,
    cancelled: bool,
    html_files: list[Path],
    records: list[dict[str, Any]],
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    progress_log: list[str],
    resumed_files: int,
) -> dict[str, Any]:
    return {
        "format": "finiq_disclosure_html_parse_v1",
        "mode": mode,
        "input_directory": str(input_directory),
        "output_path": str(output_path),
        "cancelled": cancelled,
        "summary": {
            "found_files": len(html_files),
            "parsed_files": len(records),
            "failed_files": len(errors),
            "resumed_files": resumed_files,
        },
        "records": _resolve_correction_family_acpt_numbers(records),
        "errors": errors,
        "warnings": warnings,
        "progress_log": progress_log[-200:],
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
        input_directory=request.input_directory,
        output_path=request.output_path,
        cancelled=cancelled,
        html_files=request.html_files,
        records=state.records,
        errors=state.errors,
        warnings=state.warnings,
        progress_log=state.progress_log,
        resumed_files=state.resumed_files,
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


def _resolve_parse_result_path(path: Path, mode: str) -> Path:
    if path.is_dir():
        # Try all supported modes if one is not active or if we want to be smart
        modes_to_try = (
            [mode] if mode in PARSER_REGISTRY else list(PARSER_REGISTRY.keys())
        )
        for m in modes_to_try:
            candidate = path / f"parsed-{m}.json"
            if candidate.is_file():
                return candidate

        # Fallback to the requested mode's default name even if not exists (for error reporting)
        return path / f"parsed-{mode if mode else 'bond_issuance'}.json"
    return path


def _compact_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in {"raw_tables", "raw_rows"}
    }


def _build_preview_record(
    record: dict[str, Any], *, index: int, mode: str
) -> dict[str, Any]:
    compact_record = _compact_record(record)
    return {
        "index": index,
        "title": record.get("title") or "",
        "acpt_no": record.get("acpt_no") or "",
        "rcept_no": record.get("rcept_no") or "",
        "source_file": record.get("source_file") or "",
        "source_preview": _load_source_preview(record, mode=mode),
        "parsed_result": compact_record,
    }


def _record_parse_warnings(record: dict[str, Any]) -> list[str]:
    warnings = record.get("parse_warnings")
    if not isinstance(warnings, list):
        return []
    return [str(warning).strip() for warning in warnings if str(warning).strip()]


def _restore_resume_state(request: ParseRequest, state: ParseRunState) -> None:
    if not request.resume:
        return
    existing_payload = _load_existing_parse_payload(request.output_path, request.mode)
    if existing_payload is None:
        return

    state.records = [
        _apply_manifest_metadata(
            record,
            request.manifest_metadata_index,
            mode=request.mode,
        )
        for record in list(existing_payload.get("records") or [])
        if isinstance(record, dict)
    ]
    state.errors = list(existing_payload.get("errors") or [])
    state.warnings = list(existing_payload.get("warnings") or [])
    state.processed_files = _processed_source_files(state.records, state.errors)
    state.resumed_files = len(state.processed_files)
    state.emit(f"기존 파싱 결과에서 {state.resumed_files}건을 이어받았습니다.")


def _emit_run_header(request: ParseRequest, state: ParseRunState) -> None:
    state.emit(f"파싱 대상 HTML {len(request.html_files)}건을 찾았습니다.")
    state.emit(f"파싱 모드: {request.mode}")
    state.emit(f"이어하기: {'예' if request.resume else '아니오'}")
    state.emit(f"진행 확인 간격: {request.progress_interval}건")


def _should_skip_for_resume(
    request: ParseRequest,
    state: ParseRunState,
    *,
    source_file: str,
    index: int,
) -> bool:
    if source_file not in state.processed_files:
        return False
    state.skipped_resume_count += 1
    if state.skipped_resume_count % request.progress_interval == 0:
        state.emit(
            f"이어하기 건너뜀 중간 확인: {state.skipped_resume_count}/{state.resumed_files}건 "
            f"(현재 위치 {index}/{len(request.html_files)})."
        )
    return True


def _add_parse_warning(
    request: ParseRequest,
    state: ParseRunState,
    *,
    index: int,
    html_file: Path,
    source_file: str,
    warning: str,
) -> None:
    warning_info = {
        "index": index,
        "total": len(request.html_files),
        "mode": request.mode,
        "source_file": source_file,
        "source_name": html_file.name,
        "warning": warning,
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
    if _should_skip_for_resume(request, state, source_file=source_file, index=index):
        return

    try:
        parsed_record = _compact_record(
            request.parser(html_file.read_bytes(), file_path=html_file)
        )
        for warning in _record_parse_warnings(parsed_record):
            _add_parse_warning(
                request,
                state,
                index=index,
                html_file=html_file,
                source_file=source_file,
                warning=warning,
            )
        state.records.append(
            _apply_manifest_metadata(
                parsed_record,
                request.manifest_metadata_index,
                mode=request.mode,
            )
        )
        state.processed_files.add(source_file)
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
        state.processed_files.add(source_file)

    state.processed_this_run += 1
    if state.processed_this_run % request.progress_interval == 0:
        _write_parse_payload(
            _payload_from_state(request, state, cancelled=False), request.output_path
        )
        state.emit(
            f"파싱 중간 확인: 이번 실행 {state.processed_this_run}건 처리, 결과 JSON 저장 완료."
        )


def _emit_resume_footer(request: ParseRequest, state: ParseRunState) -> None:
    if (
        state.skipped_resume_count
        and state.skipped_resume_count % request.progress_interval != 0
    ):
        state.emit(
            f"이어하기 건너뜀 완료: {state.skipped_resume_count}/{state.resumed_files}건."
        )


def parse_disclosure_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Parse downloaded KIND viewer HTML files with the selected mode parser."""
    request = _build_parse_request(body)
    state = ParseRunState(progress_callback=progress_callback)
    _clear_cancel_token(request.cancel_token)
    _restore_resume_state(request, state)
    _emit_run_header(request, state)

    try:
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

    _emit_resume_footer(request, state)
    state.emit(f"파싱 결과 JSON 저장 중: {request.output_path}")
    state.emit(f"파싱 결과 JSON 저장 완료: {request.output_path}")

    payload = _payload_from_state(request, state, cancelled=cancelled)
    _write_parse_payload(payload, request.output_path)
    return payload




__all__ = [name for name in globals() if not name.startswith("__")]
