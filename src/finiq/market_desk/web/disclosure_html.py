"""KIND disclosure viewer HTML download helpers for the web UI."""

from __future__ import annotations

from pathlib import Path
from threading import Lock
from typing import Any, Callable

from finiq.data_scraper.core.client import download_disclosure_viewer_htmls
from finiq.data_scraper.core.constants import DEFAULT_REQUEST_HEADERS

ACPT_NUMBER_KEYS = {"acpt_no", "acptno", "acptNo", "acpt_no_list", "acptNumbers"}
HTML_MANIFEST_FILENAME = "kind_disclosure_html_manifest.json"
_CANCELLED_DOWNLOADS: set[str] = set()
_CANCEL_LOCK = Lock()
ProgressCallback = Callable[[str], None]


def cancel_disclosure_html_download(token: str) -> dict[str, Any]:
    normalized_token = str(token or "").strip()
    if not normalized_token:
        msg = "cancel_token is required"
        raise ValueError(msg)
    with _CANCEL_LOCK:
        _CANCELLED_DOWNLOADS.add(normalized_token)
    return {"cancelled": True, "cancel_token": normalized_token}


def _clear_cancel_token(token: str | None) -> None:
    if not token:
        return
    with _CANCEL_LOCK:
        _CANCELLED_DOWNLOADS.discard(token)


def _is_cancelled(token: str | None) -> bool:
    if not token:
        return False
    with _CANCEL_LOCK:
        return token in _CANCELLED_DOWNLOADS


def collect_acpt_numbers_from_json(value: Any) -> list[str]:
    """Collect unique KIND receipt numbers from nested JSON-like data."""
    numbers: list[str] = []
    seen: set[str] = set()

    def add(raw_value: object) -> None:
        normalized = str(raw_value or "").strip()
        if not normalized or not normalized.isdigit() or normalized in seen:
            return
        seen.add(normalized)
        numbers.append(normalized)

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in ACPT_NUMBER_KEYS:
                    if isinstance(child, list):
                        for child_item in child:
                            add(child_item)
                    else:
                        add(child)
                visit(child)
            return
        if isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return numbers


def _collect_disclosure_metadata_from_json(value: Any) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}

    def acpt_no_from(item: dict[str, Any]) -> str:
        for key in ("acpt_no", "acptno", "acptNo"):
            normalized = str(item.get(key) or "").strip()
            if normalized.isdigit():
                return normalized
        return ""

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            acpt_no = acpt_no_from(item)
            if acpt_no and acpt_no not in metadata:
                metadata[acpt_no] = {
                    "acpt_no": acpt_no,
                    "market": item.get("market"),
                    "company_name": item.get("company_name"),
                    "company_id": item.get("company_id"),
                    "disclosed_at": item.get("disclosed_at"),
                    "title": item.get("title"),
                }
            for child in item.values():
                visit(child)
            return
        if isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return metadata


def _write_html_manifest(
    *,
    output_directory: Path,
    source_json_path: str,
    acpt_numbers: list[str],
    source_json: Any,
) -> Path:
    import json

    metadata = _collect_disclosure_metadata_from_json(source_json)
    disclosures = [
        metadata.get(acpt_no, {"acpt_no": acpt_no})
        for acpt_no in acpt_numbers
    ]
    manifest_path = output_directory / HTML_MANIFEST_FILENAME
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_html_manifest_v1",
                "source_json_path": source_json_path,
                "disclosures": disclosures,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def _parse_progress_interval(value: Any) -> int:
    if value in (None, ""):
        return 10
    parsed = int(value)
    if parsed < 1:
        msg = "progress_interval must be >= 1"
        raise ValueError(msg)
    return parsed


def download_disclosure_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Download KIND viewer HTML files for receipt numbers found in the request JSON."""
    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        msg = "output_directory is required"
        raise ValueError(msg)

    source_json = body.get("json")
    if source_json is None:
        source_json = body.get("payload")
    source_json_path = body.get("source_json_path")
    resolved_source_json_path = ""
    if not source_json_path and isinstance(source_json, dict):
        source_json_path = source_json.get("source_json_path")
    if source_json_path:
        source_json_file = Path(str(source_json_path)).expanduser().resolve()
        if not source_json_file.is_file():
            msg = f"source_json_path does not exist: {source_json_file}"
            raise ValueError(msg)
        import json

        resolved_source_json_path = str(source_json_file)
        source_json = json.loads(source_json_file.read_text(encoding="utf-8"))
    if source_json is None:
        msg = "json is required"
        raise ValueError(msg)

    acpt_numbers = collect_acpt_numbers_from_json(source_json)
    if not acpt_numbers:
        msg = "No acpt_no values found in JSON"
        raise ValueError(msg)

    limit = body.get("limit")
    if limit not in (None, ""):
        parsed_limit = int(limit)
        if parsed_limit < 1:
            msg = "limit must be >= 1"
            raise ValueError(msg)
        acpt_numbers = acpt_numbers[:parsed_limit]

    cancel_token = str(body.get("cancel_token") or "").strip() or None
    _clear_cancel_token(cancel_token)

    resolved_output_directory = Path(output_directory).expanduser().resolve()
    progress_interval = _parse_progress_interval(body.get("progress_interval"))
    progress_log: list[str] = []
    processed_count = 0

    def emit(message: str) -> None:
        progress_log.append(message)
        if progress_callback is not None:
            progress_callback(message)

    def handle_progress(message: str) -> None:
        nonlocal processed_count
        if message.startswith(("Saved KIND viewer HTML ", "Skipping existing KIND viewer HTML ")):
            processed_count += 1
            if processed_count % progress_interval == 0:
                emit(f"HTML 저장 중간 확인: {processed_count}/{len(acpt_numbers)}건 처리.")
            return
        if message.startswith("Fetching KIND viewer HTML "):
            return
        emit(message)

    emit(f"HTML 저장 대상 접수번호 {len(acpt_numbers)}건을 준비했습니다.")
    emit(f"저장 경로: {resolved_output_directory}")
    emit(f"기존 파일 건너뛰기: {'예' if bool(body.get('skip_existing', True)) else '아니오'}")
    emit(f"이어하기 방식: 저장된 HTML 파일 건너뛰기")
    emit(f"진행 확인 간격: {progress_interval}건")
    try:
        saved_paths = download_disclosure_viewer_htmls(
            output_directory=resolved_output_directory,
            request_headers=DEFAULT_REQUEST_HEADERS,
            acpt_numbers=acpt_numbers,
            timeout=float(body.get("timeout") or 20.0),
            wait_seconds_between_requests=float(body.get("wait_seconds") or 0.0),
            max_requests_per_minute=int(body.get("max_requests_per_minute") or 90),
            skip_existing=bool(body.get("skip_existing", True)),
            progress_callback=handle_progress,
            cancel_check=lambda: _is_cancelled(cancel_token),
            max_workers=int(body.get("max_workers") or 5),
            max_retries=int(body.get("max_retries") or 2),
        )
        cancelled = _is_cancelled(cancel_token)
    finally:
        _clear_cancel_token(cancel_token)
    manifest_path = _write_html_manifest(
        output_directory=resolved_output_directory,
        source_json_path=resolved_source_json_path,
        acpt_numbers=acpt_numbers,
        source_json=source_json,
    )
    emit(f"HTML 메타데이터 저장 완료: {manifest_path}")
    emit(f"HTML 저장 {'중지' if cancelled else '완료'}: 저장 파일 {len(saved_paths)}/{len(acpt_numbers)}건.")
    return {
        "format": "kind_disclosure_html_download_v1",
        "output_directory": str(resolved_output_directory),
        "requested_count": len(acpt_numbers),
        "saved_count": len(saved_paths),
        "cancelled": cancelled,
        "acpt_numbers": acpt_numbers,
        "saved_files": [str(path) for path in saved_paths],
        "manifest_path": str(manifest_path),
        "progress_log": progress_log[-100:],
    }
