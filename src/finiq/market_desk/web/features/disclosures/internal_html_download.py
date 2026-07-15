"""Disclosure internal HTML download helpers."""

from __future__ import annotations

from finiq.data_scraper.core.html_rate_limit import (
    RequestSpacingLimiter,
    wait_for_html_download_request_slot,
)
from finiq.market_desk.web.features.disclosures.html_common import *


def _fetch_internal_html(
    session: requests.Session,
    *,
    acpt_no: str,
    doc_no: str,
    request_headers: dict[str, str],
    timeout: float,
    before_request: Callable[[], None] | None = None,
) -> bytes:
    if before_request is not None:
        before_request()
    contents_response = session.get(
        KIND_DISCLOSURE_VIEWER_URL,
        params={"method": "searchContents", "docNo": doc_no},
        headers=request_headers,
        timeout=timeout,
    )
    contents_response.raise_for_status()
    paths = search_paths(contents_response.content)
    if paths is None or not paths.get("doc_loc_path"):
        msg = f"content path not found for acpt_no={acpt_no} doc_no={doc_no}"
        raise ValueError(msg)

    if before_request is not None:
        before_request()
    body_response = session.get(
        paths["doc_loc_path"], headers=request_headers, timeout=timeout
    )
    body_response.raise_for_status()
    return body_response.content


def _load_compressed_external_html_payload(
    source_directory: Path,
) -> dict[str, Any] | None:
    compressed_file = source_directory / COMPRESSED_EXTERNAL_HTML_FILENAME
    if not compressed_file.is_file():
        return None

    payload = json.loads(compressed_file.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"compressed external HTML JSON is not an object: {compressed_file}"
        raise ValueError(msg)
    if not isinstance(payload.get("records"), list):
        msg = f"compressed external HTML JSON records is not a list: {compressed_file}"
        raise ValueError(msg)
    payload = dict(payload)
    payload["source_json_path"] = str(compressed_file)
    return payload


def _load_compressed_external_html_file_payload(source_path: Path) -> dict[str, Any]:
    if not source_path.is_file():
        msg = f"source_compressed_json_path does not exist: {source_path}"
        raise ValueError(msg)
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        msg = f"compressed external HTML JSON is not an object: {source_path}"
        raise ValueError(msg)
    file_records = payload.get("records")
    if not isinstance(file_records, list):
        msg = (
            "공시원문 내부 저장 파일 입력에는 문서 JSON 압축 결과 파일"
            f"({COMPRESSED_EXTERNAL_HTML_FILENAME})을 선택해야 합니다: {source_path}"
        )
        raise ValueError(msg)
    payload = dict(payload)
    payload["source_json_path"] = str(source_path)
    return payload


def _collect_internal_targets_from_compressed_payload(
    payload: dict[str, Any],
) -> tuple[list[dict[str, str]], Any]:
    targets: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in payload.get("records") or []:
        if not isinstance(record, dict):
            continue
        acpt_no = str(record.get("acpt_no") or "").strip()
        if not acpt_no.isdigit() or acpt_no in seen:
            continue
        doc_no = ""
        for document in record.get("docs") or []:
            if not isinstance(document, dict):
                continue
            if str(document.get("select_id") or "").strip() != "mainDoc":
                continue
            candidate = str(document.get("doc_no") or "").strip()
            if candidate and document.get("selected"):
                doc_no = candidate
                break
        if not doc_no:
            doc_no = str(record.get("selected_main_doc_no") or "").strip()
        if not doc_no:
            for document in record.get("docs") or []:
                if not isinstance(document, dict):
                    continue
                if str(document.get("select_id") or "").strip() != "mainDoc":
                    continue
                candidate = str(document.get("doc_no") or "").strip()
                if candidate:
                    doc_no = candidate
                    break
        if not doc_no:
            for main_doc in record.get("main_docs") or []:
                if not isinstance(main_doc, dict):
                    continue
                candidate = str(main_doc.get("doc_no") or "").strip()
                if candidate:
                    doc_no = candidate
                    break
        if not doc_no:
            msg = f"selected main docNo not found in compressed external HTML JSON: {acpt_no}"
            raise ValueError(msg)
        year = str(record.get("year") or "").strip() or _year_from_disclosure(
            acpt_no,
            record.get("metadata")
            if isinstance(record.get("metadata"), dict)
            else None,
        )
        targets.append({"acpt_no": acpt_no, "doc_no": doc_no, "year": year})
        seen.add(acpt_no)
    if not targets:
        msg = "No internal HTML targets found in compressed external HTML JSON"
        raise ValueError(msg)
    return targets, payload


def _collect_internal_cleanup_targets_from_compressed_payload(
    payload: dict[str, Any],
) -> tuple[list[dict[str, str]], Any]:
    targets: list[dict[str, str]] = []
    seen: set[str] = set()
    for record in payload.get("records") or []:
        if not isinstance(record, dict):
            continue
        acpt_no = str(record.get("acpt_no") or "").strip()
        if not acpt_no.isdigit() or acpt_no in seen:
            continue
        year = str(record.get("year") or "").strip() or _year_from_disclosure(
            acpt_no,
            record.get("metadata")
            if isinstance(record.get("metadata"), dict)
            else None,
        )
        targets.append({"acpt_no": acpt_no, "doc_no": "", "year": year})
        seen.add(acpt_no)
    if not targets:
        msg = "No internal HTML targets found in compressed external HTML JSON"
        raise ValueError(msg)
    return targets, payload


def _collect_internal_targets_from_external_directory(
    source_directory: Path,
) -> tuple[list[dict[str, str]], Any]:
    if not source_directory.is_dir():
        msg = f"source_directory does not exist: {source_directory}"
        raise ValueError(msg)

    import json

    manifest_path = source_directory / HTML_MANIFEST_FILENAME
    manifest_payload: Any = None
    manifest_order: list[str] = []
    if manifest_path.is_file():
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        for disclosure in manifest_payload.get("disclosures") or []:
            if not isinstance(disclosure, dict):
                continue
            acpt_no = str(disclosure.get("acpt_no") or "").strip()
            if acpt_no.isdigit():
                manifest_order.append(acpt_no)

    compressed_payload = _load_compressed_external_html_payload(source_directory)
    if compressed_payload is not None:
        return _collect_internal_targets_from_compressed_payload(compressed_payload)

    target_by_acpt_no: dict[str, dict[str, str]] = {}
    html_paths = []
    for year_directory in sorted(
        path for path in source_directory.iterdir() if path.is_dir()
    ):
        if len(year_directory.name) == 4 and year_directory.name.isdigit():
            html_paths.extend(sorted(year_directory.glob("*.html")))
    for html_path in html_paths:
        acpt_no = html_path.stem
        if not acpt_no.isdigit():
            continue
        doc_no = dart_main_doc_no(html_path.read_bytes())
        if not doc_no:
            msg = f"selected main docNo not found in external HTML: {html_path}"
            raise ValueError(msg)
        year = html_path.parent.name
        target_by_acpt_no[acpt_no] = {
            "acpt_no": acpt_no,
            "doc_no": doc_no,
            "year": year,
        }

    ordered_acpt_numbers = [
        acpt_no for acpt_no in manifest_order if acpt_no in target_by_acpt_no
    ]
    ordered_acpt_numbers.extend(
        acpt_no
        for acpt_no in sorted(target_by_acpt_no)
        if acpt_no not in set(ordered_acpt_numbers)
    )
    targets = [target_by_acpt_no[acpt_no] for acpt_no in ordered_acpt_numbers]
    if not targets:
        msg = "No external HTML files found in source_directory"
        raise ValueError(msg)
    return targets, manifest_payload


def _collect_internal_cleanup_targets_from_external_directory(
    source_directory: Path,
) -> tuple[list[dict[str, str]], Any]:
    if not source_directory.is_dir():
        msg = f"source_directory does not exist: {source_directory}"
        raise ValueError(msg)

    manifest_path = source_directory / HTML_MANIFEST_FILENAME
    manifest_payload: Any = None
    manifest_order: list[str] = []
    if manifest_path.is_file():
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        for disclosure in manifest_payload.get("disclosures") or []:
            if not isinstance(disclosure, dict):
                continue
            acpt_no = str(disclosure.get("acpt_no") or "").strip()
            if acpt_no.isdigit():
                manifest_order.append(acpt_no)

    compressed_payload = _load_compressed_external_html_payload(source_directory)
    if compressed_payload is not None:
        return _collect_internal_cleanup_targets_from_compressed_payload(
            compressed_payload
        )

    html_paths = []
    for year_directory in sorted(
        path for path in source_directory.iterdir() if path.is_dir()
    ):
        if len(year_directory.name) == 4 and year_directory.name.isdigit():
            html_paths.extend(sorted(year_directory.glob("*.html")))
    target_by_acpt_no: dict[str, dict[str, str]] = {}
    for html_path in html_paths:
        acpt_no = html_path.stem
        if not acpt_no.isdigit():
            continue
        year = html_path.parent.name
        target_by_acpt_no[acpt_no] = {"acpt_no": acpt_no, "doc_no": "", "year": year}

    ordered_acpt_numbers = [
        acpt_no for acpt_no in manifest_order if acpt_no in target_by_acpt_no
    ]
    ordered_acpt_numbers.extend(
        acpt_no
        for acpt_no in sorted(target_by_acpt_no)
        if acpt_no not in set(ordered_acpt_numbers)
    )
    targets = [target_by_acpt_no[acpt_no] for acpt_no in ordered_acpt_numbers]
    if not targets:
        msg = "No external HTML files found in source_directory"
        raise ValueError(msg)
    return targets, manifest_payload


def download_disclosure_internal_htmls(
    *,
    output_directory: Path,
    request_headers: dict[str, object],
    targets: list[dict[str, str]],
    timeout: float = 20.0,
    wait_seconds_between_requests: float = 0.0,
    max_requests_per_minute: int = 90,
    skip_existing: bool = True,
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[Path]:
    """Download selected KIND disclosure body HTML files for receipt numbers."""
    if timeout <= 0:
        msg = "timeout must be > 0"
        raise ValueError(msg)
    if wait_seconds_between_requests < 0:
        msg = "wait_seconds_between_requests must be >= 0"
        raise ValueError(msg)
    if max_requests_per_minute < 1 or max_requests_per_minute > 100:
        msg = "max_requests_per_minute must be between 1 and 100"
        raise ValueError(msg)

    output_directory = output_directory.resolve()
    normalized_headers = {
        str(key): str(value) for key, value in request_headers.items()
    }
    saved_paths: list[Path] = []
    min_interval_seconds = max(
        wait_seconds_between_requests, 60.0 / max_requests_per_minute
    )
    spacing_limiter = RequestSpacingLimiter(min_interval_seconds)

    def wait_for_request() -> None:
        if wait_for_html_download_request_slot(
            cancel_check,
            spacing_limiter=spacing_limiter,
        ):
            raise InterruptedError("internal HTML download cancelled")

    with requests.Session() as session:
        for target in targets:
            acpt_no = target["acpt_no"]
            doc_no = target["doc_no"]
            if cancel_check is not None and cancel_check():
                break
            output_path = output_directory / VIEWER_HTML_FILENAME_TEMPLATE.format(
                acpt_no=acpt_no
            )
            if skip_existing and _is_valid_html(output_path):
                if progress_callback is not None:
                    progress_callback(
                        f"Skipping existing KIND internal HTML: {output_path}"
                    )
                saved_paths.append(output_path)
                continue
            if progress_callback is not None:
                progress_callback(
                    f"Fetching KIND internal HTML acpt_no={acpt_no} doc_no={doc_no}..."
                )
            try:
                internal_html = _fetch_internal_html(
                    session,
                    acpt_no=acpt_no,
                    doc_no=doc_no,
                    request_headers=normalized_headers,
                    timeout=timeout,
                    before_request=wait_for_request,
                )
            except InterruptedError:
                break
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(internal_html)
            if not _is_valid_html(output_path):
                output_path.unlink(missing_ok=True)
                raise ValueError(
                    f"Downloaded internal response for acpt_no={acpt_no} is invalid HTML"
                )
            saved_paths.append(output_path)
            if progress_callback is not None:
                progress_callback(f"Saved KIND internal HTML to: {output_path}")
    return saved_paths


def download_disclosure_internal_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Download selected KIND disclosure body HTML files for receipt numbers."""
    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        msg = "output_directory is required"
        raise ValueError(msg)

    source_directory_raw = str(body.get("source_directory") or "").strip()
    source_compressed_json_path_raw = str(
        body.get("source_compressed_json_path") or ""
    ).strip()
    if source_directory_raw and source_compressed_json_path_raw:
        msg = "source_directory and source_compressed_json_path cannot be used together"
        raise ValueError(msg)
    if not source_directory_raw and not source_compressed_json_path_raw:
        msg = "source_directory or source_compressed_json_path is required"
        raise ValueError(msg)
    if source_compressed_json_path_raw:
        source_path = Path(source_compressed_json_path_raw).expanduser().resolve()
        compressed_payload = _load_compressed_external_html_file_payload(source_path)
        targets, manifest_payload = _collect_internal_targets_from_compressed_payload(
            compressed_payload
        )
    else:
        source_path = Path(source_directory_raw).expanduser().resolve()
        targets, manifest_payload = _collect_internal_targets_from_external_directory(
            source_path,
        )

    targets = _apply_limit_to_targets(targets, body.get("limit"))
    acpt_numbers = [target["acpt_no"] for target in targets]
    target_years = {
        target["acpt_no"]: target.get("year")
        or _year_from_disclosure(target["acpt_no"])
        for target in targets
    }
    source_json = manifest_payload or {
        "disclosures": [{"acpt_no": acpt_no} for acpt_no in acpt_numbers]
    }

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
        if message.startswith(
            ("Saved KIND internal HTML ", "Skipping existing KIND internal HTML")
        ):
            processed_count += 1
            emit(message)
            if processed_count % progress_interval == 0:
                emit(
                    f"HTML 내부 저장 중간 확인: {processed_count}/{len(acpt_numbers)}건 처리."
                )
            return
        if message.startswith("Fetching KIND internal HTML "):
            emit(message)
            return
        emit(message)

    emit(f"HTML 내부 저장 대상 접수번호 {len(acpt_numbers)}건을 준비했습니다.")
    emit(f"외부 HTML 경로: {source_path}")
    emit(f"저장 경로: {resolved_output_directory}")
    emit(
        f"기존 파일 건너뛰기: {'예' if bool(body.get('skip_existing', True)) else '아니오'}"
    )
    emit(f"이어하기 방식: 저장된 HTML 파일 건너뛰기")
    emit(f"진행 확인 간격: {progress_interval}건")
    existing_paths_by_acpt_no: dict[str, Path] = {}
    download_acpt_numbers = acpt_numbers
    if bool(body.get("skip_existing", True)):
        output_summary = _validate_html_output_directory_files(
            resolved_output_directory,
            acpt_numbers,
            target_years=target_years,
        )
        existing_acpt_numbers = output_summary["existing_target_acpt_numbers"]
        download_acpt_numbers = output_summary["missing_target_acpt_numbers"]
        existing_paths_by_acpt_no = {
            acpt_no: _target_html_path(
                resolved_output_directory,
                acpt_no,
                target_years=target_years,
            )
            for acpt_no in existing_acpt_numbers
        }
        emit("저장 디렉토리 검사 완료: 대상 HTML/메타데이터 외 파일 없음.")
        emit(
            "기존 HTML 겹침 확인: "
            f"{output_summary['existing_target_html_count']}/{len(acpt_numbers)}건."
        )
        if output_summary["existing_target_html_count"] == 0:
            emit("기존 HTML 겹침 없음: 전체 대상이 새로 저장됩니다.")
        elif output_summary["missing_target_html_count"] == 0:
            emit("기존 HTML 겹침: 전체 대상이 이미 저장되어 있습니다.")
        else:
            emit(f"새로 저장할 대상: {output_summary['missing_target_html_count']}건.")
        for acpt_no, path in existing_paths_by_acpt_no.items():
            handle_progress(f"Skipping existing KIND internal HTML: {path}")
    try:
        downloaded_paths = []
        if download_acpt_numbers:
            target_by_acpt_no = {target["acpt_no"]: target for target in targets}
            grouped_targets: dict[str, list[dict[str, str]]] = {}
            for acpt_no in download_acpt_numbers:
                target = target_by_acpt_no[acpt_no]
                grouped_targets.setdefault(target_years[acpt_no], []).append(target)
            for year, group_targets in grouped_targets.items():
                downloaded_paths.extend(
                    download_disclosure_internal_htmls(
                        output_directory=resolved_output_directory / year,
                        request_headers=DEFAULT_REQUEST_HEADERS,
                        targets=[
                            {"acpt_no": target["acpt_no"], "doc_no": target["doc_no"]}
                            for target in group_targets
                        ],
                        timeout=float(body.get("timeout") or 20.0),
                        wait_seconds_between_requests=float(
                            body.get("wait_seconds") or 0.0
                        ),
                        max_requests_per_minute=int(
                            body.get("max_requests_per_minute") or 90
                        ),
                        skip_existing=False,
                        progress_callback=handle_progress,
                        cancel_check=lambda: _is_cancelled(cancel_token)
                        or bool(cancel_check and cancel_check()),
                    )
                )
        saved_paths_by_acpt_no = dict(existing_paths_by_acpt_no)
        saved_paths_by_acpt_no.update({path.stem: path for path in downloaded_paths})
        saved_paths = [
            saved_paths_by_acpt_no[acpt_no]
            for acpt_no in acpt_numbers
            if acpt_no in saved_paths_by_acpt_no
        ]
        cancelled = _is_cancelled(cancel_token) or bool(cancel_check and cancel_check())
    finally:
        _clear_cancel_token(cancel_token)
    saved_acpt_numbers = [path.stem for path in saved_paths]
    manifest_path = _write_html_manifest(
        output_directory=resolved_output_directory,
        source_json_path=str(source_path),
        acpt_numbers=saved_acpt_numbers,
        source_json=source_json,
    )
    emit(f"HTML 메타데이터 저장 완료: {manifest_path}")
    emit(
        f"HTML 내부 저장 {'중지' if cancelled else '완료'}: 저장 파일 {len(saved_paths)}/{len(acpt_numbers)}건."
    )
    return {
        "format": "kind_disclosure_internal_html_download_v1",
        "output_directory": str(resolved_output_directory),
        "requested_count": len(acpt_numbers),
        "saved_count": len(saved_paths),
        "cancelled": cancelled,
        "acpt_numbers": acpt_numbers,
        "saved_files": [str(path) for path in saved_paths],
        "manifest_path": str(manifest_path),
        "progress_log": progress_log[-100:],
    }
