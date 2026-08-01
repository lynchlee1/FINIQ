"""Disclosure internal HTML download helpers."""

from __future__ import annotations

from collections import Counter

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
    if payload.get("format") != "finiq_disclosure_external_html_docs_v1":
        msg = f"compressed external HTML JSON has an invalid format: {compressed_file}"
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
    if payload.get("format") != "finiq_disclosure_external_html_docs_v1":
        msg = f"compressed external HTML JSON has an invalid format: {source_path}"
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


def _validated_compressed_records(
    payload: dict[str, Any],
) -> list[tuple[dict[str, Any], str]]:
    records = payload.get("records")
    if not isinstance(records, list):
        msg = "compressed external HTML JSON records is not a list"
        raise ValueError(msg)

    validated: list[tuple[dict[str, Any], str]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            msg = f"compressed external HTML JSON record is not an object: index={index}"
            raise ValueError(msg)
        acpt_no = str(record.get("acpt_no") or "").strip()
        if not acpt_no.isdigit():
            msg = f"invalid acpt_no in compressed external HTML JSON: index={index}"
            raise ValueError(msg)
        validated.append((record, acpt_no))

    counts = Counter(acpt_no for _record, acpt_no in validated)
    duplicate_acpt_numbers = sorted(
        acpt_no for acpt_no, count in counts.items() if count > 1
    )
    if duplicate_acpt_numbers:
        msg = (
            "duplicate acpt_no values in compressed external HTML JSON: "
            + ", ".join(duplicate_acpt_numbers[:10])
        )
        raise ValueError(msg)
    return validated


def _compressed_record_year(record: dict[str, Any], acpt_no: str) -> str:
    return _year_from_disclosure(
        acpt_no,
        record.get("metadata") if isinstance(record.get("metadata"), dict) else None,
    )


def _collect_internal_targets_from_compressed_payload(
    payload: dict[str, Any],
) -> tuple[list[dict[str, str]], Any]:
    targets: list[dict[str, str]] = []
    for record, acpt_no in _validated_compressed_records(payload):
        doc_no = str(record.get("selected_main_doc_no") or "").strip()
        if not doc_no:
            msg = f"selected main docNo not found in compressed external HTML JSON: {acpt_no}"
            raise ValueError(msg)
        year = _compressed_record_year(record, acpt_no)
        targets.append({"acpt_no": acpt_no, "doc_no": doc_no, "year": year})
    if not targets:
        msg = "No internal HTML targets found in compressed external HTML JSON"
        raise ValueError(msg)
    return targets, payload


def _collect_internal_cleanup_targets_from_compressed_payload(
    payload: dict[str, Any],
) -> tuple[list[dict[str, str]], Any]:
    targets: list[dict[str, str]] = []
    for record, acpt_no in _validated_compressed_records(payload):
        year = _compressed_record_year(record, acpt_no)
        targets.append({"acpt_no": acpt_no, "doc_no": "", "year": year})
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


def _verify_internal_download_membership(
    *,
    expected_acpt_numbers: list[str],
    saved_paths: list[Path],
    allow_missing: bool,
) -> dict[str, Any]:
    expected = set(expected_acpt_numbers)
    actual_acpt_numbers = [path.stem for path in saved_paths]
    actual = set(actual_acpt_numbers)
    counts = Counter(actual_acpt_numbers)
    duplicate_acpt_numbers = sorted(
        acpt_no for acpt_no, count in counts.items() if count > 1
    )
    missing_acpt_numbers = sorted(expected - actual)
    unexpected_acpt_numbers = sorted(actual - expected)
    passed = (
        not duplicate_acpt_numbers
        and not unexpected_acpt_numbers
        and (allow_missing or not missing_acpt_numbers)
    )
    verification = {
        "passed": passed,
        "complete": not missing_acpt_numbers,
        "expected_records": len(expected_acpt_numbers),
        "saved_records": len(actual_acpt_numbers),
        "missing_records": len(missing_acpt_numbers),
        "unexpected_records": len(unexpected_acpt_numbers),
        "duplicate_records": len(duplicate_acpt_numbers),
        "missing_acpt_numbers": missing_acpt_numbers,
        "unexpected_acpt_numbers": unexpected_acpt_numbers,
        "duplicate_acpt_numbers": duplicate_acpt_numbers,
    }
    if not passed:
        raise ValueError(
            "Internal HTML download membership does not match requested targets: "
            f"duplicates={duplicate_acpt_numbers[:10]}, "
            f"missing={missing_acpt_numbers[:10]}, "
            f"unexpected={unexpected_acpt_numbers[:10]}"
        )
    return verification


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
        target["acpt_no"]: target["year"]
        for target in targets
    }
    source_json = manifest_payload
    if source_json is None:
        source_json = {
            "format": "finiq_disclosure_html_manifest_v1",
            "disclosures": [{"acpt_no": acpt_no} for acpt_no in acpt_numbers],
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
    source_integrity_by_acpt_no: dict[str, dict[str, Any]] = {}
    download_acpt_numbers = acpt_numbers
    if bool(body.get("skip_existing", True)):
        output_summary = _validate_html_output_directory_files(
            resolved_output_directory,
            acpt_numbers,
            target_years=target_years,
        )
        integrity_summary = _inspect_html_integrity(
            resolved_output_directory,
            acpt_numbers,
            target_years=target_years,
            source_json_path=str(source_path),
            structurally_valid_acpt_numbers=output_summary[
                "existing_target_acpt_numbers"
            ],
        )
        unverified_acpt_numbers = integrity_summary[
            "hash_unverified_target_acpt_numbers"
        ]
        if unverified_acpt_numbers:
            sample = ", ".join(unverified_acpt_numbers[:10])
            raise ValueError(
                f"기준 해시가 없는 기존 내부 HTML이 {len(unverified_acpt_numbers)}건 있습니다. "
                "현재 파일을 신뢰해 기준 해시를 생성하거나 기존 파일 건너뛰기를 해제하세요. "
                f"접수번호 예시: {sample}"
            )
        existing_acpt_numbers = integrity_summary[
            "hash_verified_target_acpt_numbers"
        ]
        download_targets = set(output_summary["missing_target_acpt_numbers"])
        download_targets.update(
            integrity_summary["hash_mismatch_target_acpt_numbers"]
        )
        download_acpt_numbers = [
            acpt_no for acpt_no in acpt_numbers if acpt_no in download_targets
        ]
        source_integrity_by_acpt_no.update(
            integrity_summary["_verified_integrity_by_acpt_no"]
        )
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
        elif not download_acpt_numbers:
            emit("기존 HTML 겹침: 전체 대상이 이미 저장되어 있습니다.")
        else:
            emit(f"새로 저장할 대상: {len(download_acpt_numbers)}건.")
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
        cancelled = _is_cancelled(cancel_token) or bool(cancel_check and cancel_check())
        verification = _verify_internal_download_membership(
            expected_acpt_numbers=acpt_numbers,
            saved_paths=[*existing_paths_by_acpt_no.values(), *downloaded_paths],
            allow_missing=cancelled,
        )
        saved_paths_by_acpt_no = dict(existing_paths_by_acpt_no)
        saved_paths_by_acpt_no.update({path.stem: path for path in downloaded_paths})
        saved_paths = [
            saved_paths_by_acpt_no[acpt_no]
            for acpt_no in acpt_numbers
            if acpt_no in saved_paths_by_acpt_no
        ]
        downloaded_integrity, _ = _hash_html_files(
            {path.stem: path for path in downloaded_paths}
        )
        source_integrity_by_acpt_no.update(downloaded_integrity)
    finally:
        _clear_cancel_token(cancel_token)
    saved_acpt_numbers = [path.stem for path in saved_paths]
    manifest_path = _write_html_manifest(
        output_directory=resolved_output_directory,
        source_json_path=str(source_path),
        acpt_numbers=saved_acpt_numbers,
        source_json=source_json,
        source_integrity=source_integrity_by_acpt_no,
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
        "verification": verification,
        "progress_log": progress_log[-100:],
    }
