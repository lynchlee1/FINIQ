"""KIND disclosure viewer HTML parsing helpers for the web UI."""

from __future__ import annotations

import json
import re
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from finiq.market_desk.web.html_parsers import (
    parse_asset_transaction,
    parse_bond_issuance,
    parse_rights_issuance,
    parse_security_transaction,
    parse_shareholder_meeting,
)
from finiq.market_desk.web.disclosure_html import HTML_MANIFEST_FILENAME

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
        "발행대상자세부엔티티",
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
        "발행대상자세부엔티티",
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


def _normalize_listing_market(value: Any) -> str:
    market = str(value or "").strip()
    if market == "유가증권":
        return "코스피"
    return market


def _load_html_manifest_metadata_index(input_directory: Path) -> dict[str, dict[str, str]]:
    manifest_path = input_directory / HTML_MANIFEST_FILENAME
    if not manifest_path.is_file():
        return {}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"HTML 메타데이터 manifest를 읽을 수 없습니다: {manifest_path}") from exc
    if not isinstance(payload, dict):
        return {}
    metadata_index: dict[str, dict[str, str]] = {}
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


def _apply_manifest_metadata(
    record: dict[str, Any],
    metadata_index: dict[str, dict[str, str]],
    *,
    mode: str,
) -> dict[str, Any]:
    acpt_no = str(record.get("acpt_no") or "").strip()
    metadata = metadata_index.get(acpt_no) or {}
    market = metadata.get("market")
    company_name = metadata.get("company_name")
    if not market and not company_name:
        return record
    updated_record = dict(record)
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
    files = sorted(path for path in input_directory.iterdir() if path.is_file() and path.suffix.lower() == ".html")
    return files[:limit] if limit is not None else files


def _load_existing_parse_payload(output_path: Path, mode: str) -> dict[str, Any] | None:
    if not output_path.is_file():
        return None
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"기존 파싱 결과 JSON을 읽을 수 없습니다: {output_path}") from exc
    if not isinstance(payload, dict) or payload.get("format") != "finiq_disclosure_html_parse_v1":
        return None
    if payload.get("mode") != mode:
        return None
    return payload


def _processed_source_files(records: list[dict[str, Any]], errors: list[dict[str, Any]]) -> set[str]:
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


def _resolve_correction_family_acpt_numbers(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
        modes_to_try = [mode] if mode in PARSER_REGISTRY else list(PARSER_REGISTRY.keys())
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


def _record_parse_warnings(record: dict[str, Any]) -> list[str]:
    warnings = record.get("parse_warnings")
    if not isinstance(warnings, list):
        return []
    return [str(warning).strip() for warning in warnings if str(warning).strip()]


def parse_disclosure_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Parse downloaded KIND viewer HTML files with the selected mode parser."""
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
    if output_path_raw:
        output_path = Path(output_path_raw).expanduser().resolve()
    else:
        output_path = input_directory / f"parsed-{mode}.json"

    limit = _parse_limit(body.get("limit"))
    skip_errors = bool(body.get("skip_errors", True))
    resume = bool(body.get("resume", True))
    progress_interval = _parse_progress_interval(body.get("progress_interval"))
    cancel_token = str(body.get("cancel_token") or "").strip() or None
    _clear_cancel_token(cancel_token)
    html_files = _collect_html_files(input_directory, limit)
    manifest_metadata_index = _load_html_manifest_metadata_index(input_directory)

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    progress_log: list[str] = []
    resumed_files = 0
    processed_files: set[str] = set()

    def emit(message: str) -> None:
        progress_log.append(message)
        if progress_callback is not None:
            progress_callback(message)

    if resume:
        existing_payload = _load_existing_parse_payload(output_path, mode)
        if existing_payload is not None:
            records = [
                _apply_manifest_metadata(
                    record,
                    manifest_metadata_index,
                    mode=mode,
                )
                for record in list(existing_payload.get("records") or [])
                if isinstance(record, dict)
            ]
            errors = list(existing_payload.get("errors") or [])
            warnings = list(existing_payload.get("warnings") or [])
            processed_files = _processed_source_files(records, errors)
            resumed_files = len(processed_files)
            emit(f"기존 파싱 결과에서 {resumed_files}건을 이어받았습니다.")

    emit(f"파싱 대상 HTML {len(html_files)}건을 찾았습니다.")
    emit(f"파싱 모드: {mode}")
    emit(f"이어하기: {'예' if resume else '아니오'}")
    emit(f"진행 확인 간격: {progress_interval}건")

    processed_this_run = 0
    skipped_resume_count = 0
    try:
        for index, html_file in enumerate(html_files, start=1):
            if _is_cancelled(cancel_token):
                emit(f"중지 요청으로 파싱을 멈췄습니다. 처리 완료 {len(records)}/{len(html_files)}건.")
                break
            source_file = str(html_file.resolve())
            if source_file in processed_files:
                skipped_resume_count += 1
                if skipped_resume_count % progress_interval == 0:
                    emit(
                        f"이어하기 건너뜀 중간 확인: {skipped_resume_count}/{resumed_files}건 "
                        f"(현재 위치 {index}/{len(html_files)})."
                    )
                continue
            try:
                parsed_record = _compact_record(parser(html_file.read_bytes(), file_path=html_file))
                parse_warnings = _record_parse_warnings(parsed_record)
                for warning in parse_warnings:
                    warning_info = {
                        "index": index,
                        "total": len(html_files),
                        "mode": mode,
                        "source_file": source_file,
                        "source_name": html_file.name,
                        "warning": warning,
                    }
                    warnings.append(warning_info)
                    emit(f"파싱 경고 {index}/{len(html_files)}: {html_file.name} {warning}")
                records.append(
                    _apply_manifest_metadata(
                        parsed_record,
                        manifest_metadata_index,
                        mode=mode,
                    )
                )
                processed_files.add(source_file)
            except Exception as exc:
                error_info = {
                    "index": index,
                    "total": len(html_files),
                    "mode": mode,
                    "source_file": str(html_file),
                    "source_name": html_file.name,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                if not skip_errors:
                    msg = (
                        f"파싱 실패 {index}/{len(html_files)}: {html_file.name} "
                        f"({error_info['error_type']}) {exc}"
                    )
                    raise ValueError(msg) from exc
                errors.append(error_info)
                emit(
                    f"파싱 실패 {index}/{len(html_files)}: {html_file.name} "
                    f"({error_info['error_type']}) {exc}"
                )
                processed_files.add(source_file)
            processed_this_run += 1
            if processed_this_run % progress_interval == 0:
                payload = _build_payload(
                    mode=mode,
                    input_directory=input_directory,
                    output_path=output_path,
                    cancelled=False,
                    html_files=html_files,
                    records=records,
                    errors=errors,
                    warnings=warnings,
                    progress_log=progress_log,
                    resumed_files=resumed_files,
                )
                _write_parse_payload(payload, output_path)
                emit(f"파싱 중간 확인: 이번 실행 {processed_this_run}건 처리, 결과 JSON 저장 완료.")
        cancelled = _is_cancelled(cancel_token)
    finally:
        _clear_cancel_token(cancel_token)

    if skipped_resume_count and skipped_resume_count % progress_interval != 0:
        emit(f"이어하기 건너뜀 완료: {skipped_resume_count}/{resumed_files}건.")
    emit(f"파싱 결과 JSON 저장 중: {output_path}")
    emit(f"파싱 결과 JSON 저장 완료: {output_path}")

    payload = _build_payload(
        mode=mode,
        input_directory=input_directory,
        output_path=output_path,
        cancelled=cancelled,
        html_files=html_files,
        records=records,
        errors=errors,
        warnings=warnings,
        progress_log=progress_log,
        resumed_files=resumed_files,
    )
    _write_parse_payload(payload, output_path)
    return payload


def _record_family_info(record: dict[str, Any]) -> tuple[str, int | None, int | None]:
    families = record.get("correction_families")
    if not isinstance(families, dict) or not families:
        return ("", None, None)
    family_id = str(next(iter(families)))
    family = families.get(family_id)
    if not isinstance(family, dict):
        return (family_id, None, None)
    current_sequence_raw = family.get("current_sequence")
    current_sequence = current_sequence_raw if isinstance(current_sequence_raw, int) else None
    members = family.get("members")
    member_count = len(members) if isinstance(members, list) else None
    return (family_id, current_sequence, member_count)


def _json_stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _field_changed(before: Any, after: Any) -> bool:
    return _json_stable(before) != _json_stable(after)


def _record_reference(record: dict[str, Any], *, index: int) -> dict[str, Any]:
    family_id, current_sequence, member_count = _record_family_info(record)
    return {
        "index": index,
        "title": record.get("title") or "",
        "source_file": record.get("source_file") or "",
        "acpt_no": record.get("acpt_no") or "",
        "rcept_no": record.get("rcept_no") or "",
        "family_id": family_id,
        "current_sequence": current_sequence,
        "family_member_count": member_count,
    }


def _sequence_sort_key(record: dict[str, Any]) -> tuple[int, str]:
    _, current_sequence, _ = _record_family_info(record)
    sequence = current_sequence if current_sequence is not None else 0
    return (sequence, str(record.get("rcept_no") or record.get("acpt_no") or ""))


def _get_all_value_fields(records: list[dict[str, Any]]) -> list[str]:
    """Dynamically discover all fields present in the records, excluding metadata."""
    all_fields = set()
    for record in records:
        all_fields.update(record.keys())
    
    # Filter out metadata and sort for consistency
    value_fields = sorted([f for f in all_fields if f not in METADATA_FIELDS])
    return value_fields


def _build_record_change(
    *,
    mode: str,
    before_record: dict[str, Any],
    after_record: dict[str, Any],
    before_index: int,
    after_index: int,
    fields: list[str] | None = None,
) -> dict[str, Any] | None:
    # Use provided fields or fallback to mode-specific or discover dynamic
    if not fields:
        fields = list(CHANGE_LOG_FIELDS.get(mode, _get_all_value_fields([before_record, after_record])))
    
    changes: list[dict[str, Any]] = []
    major_fields = MAJOR_CHANGE_FIELDS.get(mode, set())
    
    for field in fields:
        before_value = before_record.get(field)
        after_value = after_record.get(field)
        
        if not _field_changed(before_value, after_value):
            continue
            
        changes.append(
            {
                "field": field,
                "impact": "major" if field in major_fields else "minor",
                "before": before_value,
                "after": after_value,
            }
        )
        
    if not changes:
        return None
        
    severity = "major" if any(c["impact"] == "major" for c in changes) else "minor"
    return {
        "severity": severity,
        "changed_fields": len(changes),
        "major_fields": sum(1 for change in changes if change["impact"] == "major"),
        "minor_fields": sum(1 for change in changes if change["impact"] == "minor"),
        "before": _record_reference(before_record, index=before_index),
        "after": _record_reference(after_record, index=after_index),
        "changes": changes,
    }


def _parse_korean_date(date_str: Any) -> float:
    if not date_str or not isinstance(date_str, str):
        return float("nan")
    match = re.search(r"(\d{4})\s*[년.-]\s*(\d{1,2})\s*[월.-]\s*(\d{1,2})", date_str)
    if match:
        from datetime import datetime
        try:
            return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))).timestamp() * 1000
        except ValueError:
            return float("nan")
    clean = re.sub(r"[^\d]", "", date_str)
    if len(clean) == 8:
        from datetime import datetime
        try:
            return datetime(int(clean[:4]), int(clean[4:6]), int(clean[6:8])).timestamp() * 1000
        except ValueError:
            return float("nan")
    return float("nan")


def _parse_numeric_value(val: Any) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if not isinstance(val, str):
        return float("nan")
    match = re.search(r"-?\d+\.?\d*", val.replace(",", ""))
    return float(match.group(0)) if match else float("nan")


def _is_major_change(
    field: str, 
    before: Any, 
    after: Any, 
    *,
    date_thresholds: dict[str, float],
    numeric_thresholds: dict[str, float]
) -> bool:
    if _json_stable(before) == _json_stable(after):
        return False
    
    if field == "회차":
        return False

    date_threshold = date_thresholds.get(field)
    if date_threshold is not None:
        d1 = _parse_korean_date(before)
        d2 = _parse_korean_date(after)
        import math
        if not math.isnan(d1) and not math.isnan(d2):
            if abs(d1 - d2) <= date_threshold * 24 * 3600 * 1000:
                return False
    
    num_threshold = numeric_thresholds.get(field)
    if num_threshold is not None:
        n1 = _parse_numeric_value(before)
        n2 = _parse_numeric_value(after)
        import math
        if not math.isnan(n1) and not math.isnan(n2) and n2 != 0:
            diff_percent = abs((n2 - n1) / n2) * 100
            if diff_percent <= num_threshold:
                return False
                
    return True


def _get_cached_payload(path: Path) -> dict[str, Any]:
    path = path.resolve()
    path_str = str(path)
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return {}
    
    with _CACHE_LOCK:
        cached = _PARSE_CACHE.get(path_str)
        if cached and cached["mtime"] == mtime:
            return cached["payload"]
    
    payload = _load_parse_payload(path)
    
    with _CACHE_LOCK:
        if len(_PARSE_CACHE) > 10:
            _PARSE_CACHE.clear()
        _PARSE_CACHE[path_str] = {"mtime": mtime, "payload": payload}
        
    return payload


def build_parse_change_log_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Load parse results and return correction-family field changes with generic support."""
    output_path_raw = str(body.get("output_path") or body.get("parse_result_path") or "").strip()
    if not output_path_raw:
        msg = "output_path is required"
        raise ValueError(msg)
    
    requested_mode = str(body.get("mode") or "").strip()
    output_path = _resolve_parse_result_path(Path(output_path_raw).expanduser().resolve(), requested_mode)
    
    try:
        payload = _get_cached_payload(output_path)
    except Exception as exc:
        # Provide a more user-friendly error if it's a file-not-found issue
        if not output_path.exists():
            msg = f"파싱 결과 파일을 찾을 수 없습니다. 먼저 [HTML 파싱]을 진행해 주세요.\n(예상 경로: {output_path.name})"
            raise ValueError(msg) from exc
        raise

    mode = str(payload.get("mode") or "")
    summary_only = bool(body.get("summary_only"))
    requested_family_id = body.get("family_id")
    limit = _parse_limit(body.get("limit"))
    changes_only = bool(body.get("changes_only"))

    # Load thresholds from global config
    from finiq.market_desk.web.app import config as app_config
    date_thresholds = app_config.change_log_date_thresholds or {}
    numeric_thresholds = app_config.change_log_numeric_thresholds or {}

    # Get records
    all_records = list(payload.get("records") or [])
    
    # Identify which records belong to which families
    family_records: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for index, record in enumerate(all_records, start=1):
        if not isinstance(record, dict):
            continue
        family_id, current_sequence, member_count = _record_family_info(record)
        if not family_id or member_count is None or member_count < 2 or current_sequence is None:
            continue
        if requested_family_id and family_id != requested_family_id:
            continue
        family_records.setdefault(family_id, []).append((index, record))

    # Determine fields to compare: use defined ones or discover from data
    if mode in CHANGE_LOG_FIELDS:
        comparison_fields = list(CHANGE_LOG_FIELDS[mode])
    else:
        # Dynamic discovery for generic modes (like shareholder_meeting)
        comparison_fields = _get_all_value_fields(all_records)

    # If we need details, resolve acpt_numbers ONLY for the relevant records
    if not summary_only or requested_family_id:
        rcept_to_acpt = _rcept_no_to_acpt_no(all_records)
        for family_id in family_records:
            resolved_list = []
            for index, record in family_records[family_id]:
                resolved_record = dict(record)
                families_data = record.get("correction_families")
                if isinstance(families_data, dict):
                    resolved_families = {}
                    for fid, fdoc in families_data.items():
                        resolved_fdoc = dict(fdoc)
                        members = fdoc.get("members")
                        if isinstance(members, list):
                            resolved_members = []
                            for m in members:
                                if isinstance(m, dict):
                                    rm = dict(m)
                                    r_no = str(rm.get("rcept_no") or "").strip()
                                    if r_no and not rm.get("acpt_no"):
                                        rm["acpt_no"] = rcept_to_acpt.get(r_no)
                                    resolved_members.append(rm)
                                else:
                                    resolved_members.append(m)
                            resolved_fdoc["members"] = resolved_members
                        resolved_families[str(fid)] = resolved_fdoc
                    resolved_record["correction_families"] = resolved_families
                resolved_list.append((index, resolved_record))
            family_records[family_id] = resolved_list

    families: list[dict[str, Any]] = []
    # Sort families by family_id descending (latest first) for better responsiveness and early exit
    for family_id, records in sorted(family_records.items(), reverse=True):
        sorted_records = sorted(records, key=lambda item: _sequence_sort_key(item[1]))

        family_changes: list[dict[str, Any]] = []
        for (before_index, before_record), (after_index, after_record) in zip(sorted_records, sorted_records[1:]):
            change = _build_record_change(
                mode=mode,
                before_record=before_record,
                after_record=after_record,
                before_index=before_index,
                after_index=after_index,
                fields=comparison_fields,
            )
            if change is not None:
                family_changes.append(change)

        # Calculate MAJOR changed fields count and names (exclude minor changes based on thresholds)
        changed_field_names = set()
        for change in family_changes:
            for c in change["changes"]:
                f = str(c["field"]).strip()
                # Check if it's a major change based on dynamic thresholds
                if _is_major_change(
                    f, 
                    c["before"], 
                    c["after"], 
                    date_thresholds=date_thresholds, 
                    numeric_thresholds=numeric_thresholds
                ):
                    changed_field_names.add(f)
        
        total_changed_fields = len(changed_field_names)

        if changes_only and total_changed_fields == 0:
            continue

        if summary_only and not (requested_family_id == family_id):
            families.append(
                {
                    "family_id": family_id,
                    "record_count": len(sorted_records),
                    "title": sorted_records[-1][1].get("title") or "",
                    "changed_fields": total_changed_fields,
                    "changed_field_names": sorted(list(changed_field_names)),
                    "has_details": False,
                }
            )
        else:
            families.append(
                {
                    "family_id": family_id,
                    "severity": "major" if any(c["severity"] == "major" for c in family_changes) else "minor" if family_changes else "none",
                    "record_count": len(sorted_records),
                    "change_count": len(family_changes),
                    "changed_fields": total_changed_fields,
                    "changed_field_names": sorted(list(changed_field_names)),
                    "records": [_record_reference(record, index=index) for index, record in sorted_records],
                    "changes": family_changes,
                    "has_details": True,
                }
            )

        # Early exit if we reached the limit
        if limit is not None and len(families) >= limit:
            break

    visible_families = families
    return {
        "format": "finiq_parse_change_log_v1",
        "mode": mode,
        "source_path": str(output_path),
        "summary": {
            "records": len(all_records),
            "families": len(family_records) if not requested_family_id else "filtered",
            "visible_families": len(visible_families),
            "major_changes": sum(1 for family in visible_families if family.get("severity") == "major"),
            "minor_changes": sum(1 for family in visible_families if family.get("severity") == "minor"),
        },
        "families": visible_families,
    }


def build_bond_parse_summary_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Load a bond_issuance parse result JSON and return UI-ready summary rows."""
    output_path_raw = str(body.get("output_path") or body.get("parse_result_path") or "").strip()
    if not output_path_raw:
        msg = "output_path is required"
        raise ValueError(msg)
    output_path = Path(output_path_raw).expanduser().resolve()
    payload = _load_parse_payload(output_path)
    if payload.get("mode") != "bond_issuance":
        msg = "parse result mode must be bond_issuance"
        raise ValueError(msg)

    limit = _parse_limit(body.get("limit"))
    records = _resolve_correction_family_acpt_numbers(list(payload.get("records") or []))
    total_count = len(records)
    if limit is not None:
        records = records[:limit]

    summary_records: list[dict[str, Any]] = []
    families: dict[str, Any] = {}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            continue
        family_id, current_sequence, member_count = _record_family_info(record)
        for family_key, family in (record.get("correction_families") or {}).items():
            if str(family_key) and str(family_key) not in families:
                families[str(family_key)] = family
        summary_records.append(
            {
                "index": index,
                "title": record.get("title") or "",
                "source_file": record.get("source_file") or "",
                "acpt_no": record.get("acpt_no") or "",
                "rcept_no": record.get("rcept_no") or "",
                "family_id": family_id,
                "current_sequence": current_sequence,
                "family_member_count": member_count,
                "fields": {field: record.get(field) for field in BOND_SUMMARY_FIELDS},
            }
        )

    return {
        "format": "finiq_bond_parse_summary_v1",
        "source_path": str(output_path),
        "summary": {
            "records": total_count,
            "visible_records": len(summary_records),
            "families": len(families),
            "correction_records": sum(
                1 for record in summary_records if (record.get("current_sequence") or 0) > 0
            ),
            "latest_records": sum(
                1
                for record in summary_records
                if record.get("family_member_count") is not None
                and record.get("current_sequence") == record.get("family_member_count") - 1
            ),
        },
        "families": families,
        "records": summary_records,
    }


def _xlsx_column_name(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def build_parse_export_xlsx(output_path_raw: str, requested_mode: str, latest_only: bool = False) -> bytes:
    from xml.sax.saxutils import escape

    output_path = _resolve_parse_result_path(Path(output_path_raw).expanduser().resolve(), requested_mode)
    try:
        payload = _load_parse_payload(output_path)
    except Exception as exc:
        raise ValueError(f"파싱 결과 파일을 찾을 수 없습니다: {output_path.name}") from exc

    records = list(payload.get("records") or [])
    if latest_only:
        filtered_records = []
        for record in records:
            family_id, current_sequence, member_count = _record_family_info(record)
            if family_id and member_count is not None and current_sequence is not None:
                if current_sequence == member_count - 1:
                    filtered_records.append(record)
            else:
                filtered_records.append(record)
        records = filtered_records

    # Dynamic extraction of all keys
    all_keys = set()
    for record in records:
        all_keys.update(record.keys())
    
    # Priority headers
    priority = ["title", "rcept_no", "acpt_no", "source_file"]
    headers = [p for p in priority if p in all_keys] + sorted(k for k in all_keys if k not in priority and k != "correction_families" and k != "source_lines")

    workbook_rows = [headers]
    for record in records:
        row = []
        for header in headers:
            val = record.get(header)
            if isinstance(val, (list, dict)):
                row.append(json.dumps(val, ensure_ascii=False))
            elif val is None:
                row.append("")
            else:
                row.append(str(val))
        workbook_rows.append(row)

    sheet_rows_xml: list[str] = []
    for row_number, row_values in enumerate(workbook_rows, start=1):
        cell_xml: list[str] = []
        for column_number, value in enumerate(row_values, start=1):
            cell_ref = f"{_xlsx_column_name(column_number)}{row_number}"
            cell_xml.append(
                f'<c r="{cell_ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            )
        sheet_rows_xml.append(f'<row r="{row_number}">{"".join(cell_xml)}</row>')

    dimension_ref = f"A1:{_xlsx_column_name(len(headers))}{max(1, len(workbook_rows))}"
    
    col_widths = "".join(f'<col min="{i}" max="{i}" width="20" customWidth="1"/>' for i in range(1, len(headers) + 1))
    
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimension_ref}"/>'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f'<cols>{col_widths}</cols>'
        f'<sheetData>{"".join(sheet_rows_xml)}</sheetData>'
        f'<autoFilter ref="{dimension_ref}"/>'
        "</worksheet>"
    )
    
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )
    
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )

    import io
    import zipfile
    
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        
    return output.getvalue()
