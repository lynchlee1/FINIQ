"""KIND disclosure viewer HTML parsing helpers for the web UI."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any, Callable

from finiq_marketDesk.web.html_parsers import (
    parse_asset_transaction,
    parse_bond_issuance,
    parse_rights_issuance,
    parse_security_transaction,
    parse_shareholder_meeting,
)

ParseFunction = Callable[[str | bytes], dict[str, Any]]
ProgressCallback = Callable[[str], None]
_CANCELLED_PARSES: set[str] = set()
_CANCEL_LOCK = Lock()

PARSER_REGISTRY = {
    "bond_issuance": parse_bond_issuance,
    "rights_issuance": parse_rights_issuance,
    "shareholder_meeting": parse_shareholder_meeting,
    "asset_transaction": parse_asset_transaction,
    "security_transaction": parse_security_transaction,
}


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
        "progress_log": progress_log[-200:],
    }


def _write_parse_payload(payload: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _compact_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if key not in {"raw_tables", "raw_rows"}
    }


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

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
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
            records = list(existing_payload.get("records") or [])
            errors = list(existing_payload.get("errors") or [])
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
                records.append(_compact_record(parser(html_file.read_bytes(), file_path=html_file)))
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
        progress_log=progress_log,
        resumed_files=resumed_files,
    )
    _write_parse_payload(payload, output_path)
    return payload
