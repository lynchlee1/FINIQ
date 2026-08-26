"""Disclosure internal HTML download helpers."""

from __future__ import annotations

import threading
import time
from collections import Counter, deque

from finiq.data_scraper.core.html_rate_limit import (
    RequestSpacingLimiter,
    SlidingWindowRateLimiter,
    wait_for_html_download_request_slot,
)
from finiq.data_scraper.core.kind_computers import (
    KindVirtualComputer,
    build_kind_virtual_computers,
    create_kind_computer_session,
    normalize_kind_proxy_urls,
    run_kind_virtual_computers,
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
        if not acpt_no:
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


def _internal_html_virtual_computer_worker(
    computer: KindVirtualComputer,
    targets: list[dict[str, str]],
    worker_kwargs: dict[str, object],
    progress_queue: object,
    cancel_event: object,
) -> list[str]:
    paths = download_disclosure_internal_htmls(
        output_directory=Path(str(worker_kwargs["output_directory"])),
        request_headers=dict(worker_kwargs["request_headers"]),  # type: ignore[arg-type]
        targets=targets,
        timeout=float(worker_kwargs["timeout"]),
        wait_seconds_between_requests=float(
            worker_kwargs["wait_seconds_between_requests"]
        ),
        max_requests_per_minute=int(worker_kwargs["max_requests_per_minute"]),
        skip_existing=bool(worker_kwargs["skip_existing"]),
        progress_callback=lambda message: progress_queue.put(message),  # type: ignore[attr-defined]
        cancel_check=lambda: bool(cancel_event.is_set()),  # type: ignore[attr-defined]
        max_workers=int(worker_kwargs["max_workers"]),
        target_output_directories={
            target["acpt_no"]: str(
                dict(worker_kwargs["target_output_directories"])[
                    target["acpt_no"]
                ]
            )
            for target in targets
        },
        _egress_proxy_url=computer.proxy_url,
        _include_process_limiter=False,
    )
    return [str(path) for path in paths]


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
    max_workers: int | None = None,
    spacing_limiter: RequestSpacingLimiter | None = None,
    session: requests.Session | None = None,
    kind_proxy_urls: Sequence[str] | None = None,
    target_output_directories: Mapping[str, str | Path] | None = None,
    _egress_proxy_url: str | None = None,
    _include_process_limiter: bool = True,
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
    target_acpt_numbers = [target["acpt_no"] for target in targets]
    if target_output_directories is None:
        resolved_output_directories = {
            acpt_no: output_directory for acpt_no in target_acpt_numbers
        }
    else:
        if set(target_output_directories) != set(target_acpt_numbers):
            raise ValueError(
                "target_output_directories must match target acpt_numbers"
            )
        resolved_output_directories = {
            acpt_no: Path(target_output_directories[acpt_no]).resolve()
            for acpt_no in target_acpt_numbers
        }
    normalized_proxy_urls = normalize_kind_proxy_urls(kind_proxy_urls)
    if session is not None and (
        normalized_proxy_urls or _egress_proxy_url is not None
    ):
        raise ValueError("session cannot be combined with KIND proxy configuration")
    worker_count = resolve_worker_count(
        max_workers,
        item_count=len(targets),
        field_name="max_workers",
    )
    active_computer_count = min(
        len(build_kind_virtual_computers(normalized_proxy_urls)),
        len(targets),
        worker_count,
    )
    if active_computer_count > 1:
        computer_results = run_kind_virtual_computers(
            items=targets,
            worker_qualname=(
                "finiq.market_desk.web.features.disclosures."
                "internal_html_download._internal_html_virtual_computer_worker"
            ),
            worker_kwargs={
                "output_directory": str(output_directory),
                "request_headers": {
                    str(key): str(value) for key, value in request_headers.items()
                },
                "timeout": timeout,
                "wait_seconds_between_requests": wait_seconds_between_requests,
                "max_requests_per_minute": max_requests_per_minute,
                "skip_existing": skip_existing,
                "target_output_directories": {
                    acpt_no: str(path)
                    for acpt_no, path in resolved_output_directories.items()
                },
            },
            progress_callback=progress_callback,
            cancel_check=cancel_check,
            proxy_urls=normalized_proxy_urls,
            max_workers=worker_count,
        )
        saved_paths: dict[str, Path] = {}
        for result in computer_results:
            for path_value in result:
                path = Path(str(path_value))
                saved_paths[path.stem] = path
        return [
            saved_paths[target["acpt_no"]]
            for target in targets
            if target["acpt_no"] in saved_paths
        ]
    normalized_headers = {
        str(key): str(value) for key, value in request_headers.items()
    }
    if spacing_limiter is None:
        min_interval_seconds = max(
            wait_seconds_between_requests, 60.0 / max_requests_per_minute
        )
        spacing_limiter = RequestSpacingLimiter(min_interval_seconds)
    rate_limiter = SlidingWindowRateLimiter(max_requests_per_minute)
    progress_lock = Lock()

    def report(message: str) -> None:
        if progress_callback is not None:
            with progress_lock:
                progress_callback(message)

    def wait_for_request() -> None:
        if wait_for_html_download_request_slot(
            cancel_check,
            local_limiter=rate_limiter,
            spacing_limiter=spacing_limiter,
            include_process_limiter=_include_process_limiter,
        ):
            raise InterruptedError("internal HTML download cancelled")

    def download_target(
        target: dict[str, str],
        session: requests.Session,
    ) -> Path | None:
        acpt_no = target["acpt_no"]
        doc_no = target["doc_no"]
        if cancel_check is not None and cancel_check():
            return None
        output_path = resolved_output_directories[
            acpt_no
        ] / VIEWER_HTML_FILENAME_TEMPLATE.format(
            acpt_no=acpt_no
        )
        if skip_existing and _is_valid_html(output_path):
            report(f"Skipping existing KIND internal HTML: {output_path}")
            return output_path
        report(f"Fetching KIND internal HTML acpt_no={acpt_no} doc_no={doc_no}...")
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
            return None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(internal_html)
        if not _is_valid_html(output_path):
            output_path.unlink(missing_ok=True)
            raise ValueError(
                f"Downloaded internal response for acpt_no={acpt_no} is invalid HTML"
            )
        report(f"Saved KIND internal HTML to: {output_path}")
        return output_path

    worker_local = threading.local()
    worker_sessions: list[requests.Session] = []
    worker_sessions_lock = Lock()
    active_session = session
    computer = KindVirtualComputer(index=0, proxy_url=_egress_proxy_url)

    def download_parallel_target(
        item: tuple[int, dict[str, str]],
    ) -> tuple[int, Path | None]:
        index, target = item
        worker_session = active_session
        if worker_session is None:
            worker_session = getattr(worker_local, "session", None)
            if worker_session is None:
                worker_session = create_kind_computer_session(
                    computer, pool_size=worker_count
                )
                worker_local.session = worker_session
                with worker_sessions_lock:
                    worker_sessions.append(worker_session)
        return index, download_target(target, worker_session)

    indexed_paths: list[Path | None] = [None] * len(targets)
    if worker_count == 1:
        def download_serial(active: requests.Session) -> None:
            for index, target in enumerate(targets):
                path = download_target(target, active)
                indexed_paths[index] = path
                if path is None and cancel_check is not None and cancel_check():
                    break

        if active_session is None:
            with create_kind_computer_session(
                computer, pool_size=worker_count
            ) as owned_session:
                download_serial(owned_session)
        else:
            download_serial(active_session)
    else:
        try:
            with ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="kind-internal-html",
            ) as executor:
                completed = bounded_as_completed(
                    executor,
                    enumerate(targets),
                    lambda item: executor.submit(download_parallel_target, item),
                    max_pending=worker_count * 2,
                )
                for future, (index, _target) in completed:
                    result_index, path = future.result()
                    indexed_paths[result_index] = path
        finally:
            for worker_session in worker_sessions:
                worker_session.close()

    return [path for path in indexed_paths if path is not None]


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

    if "source_directory" in body:
        msg = "source_directory is not supported; use source_compressed_json_path"
        raise ValueError(msg)
    source_compressed_json_path_raw = str(
        body.get("source_compressed_json_path") or ""
    ).strip()
    if not source_compressed_json_path_raw:
        msg = "source_compressed_json_path is required"
        raise ValueError(msg)
    source_path = Path(source_compressed_json_path_raw).expanduser().resolve()
    compressed_payload = _load_compressed_external_html_file_payload(source_path)
    parent_mode_raw = body.get("parent_mode")
    if parent_mode_raw not in (None, ""):
        workspace = resolve_disclosure_workspace(body.get("data_root") or "")
        mode = validate_workspace_mode(body.get("mode"))
        parent_mode = validate_workspace_mode(parent_mode_raw)
        expected_source_path = (
            workspace.external_owner_mode(mode, parent_mode=parent_mode)
            / COMPRESSED_EXTERNAL_HTML_FILENAME
        ).resolve()
        if source_path != expected_source_path:
            raise ValueError(
                "derived filter internal HTML must use its parent's compressed "
                "external records: "
                f"{expected_source_path}"
            )
        source_json, _source_json_path = _load_workspace_filtered_payload(body)
        child_acpt_numbers = collect_acpt_numbers_from_json(source_json)
        child_acpt_numbers = _apply_limit_to_acpt_numbers(
            child_acpt_numbers, body.get("limit")
        )
        parent_records = {
            acpt_no: record
            for record, acpt_no in _validated_compressed_records(compressed_payload)
        }
        missing_records = [
            acpt_no for acpt_no in child_acpt_numbers if acpt_no not in parent_records
        ]
        if missing_records:
            raise ValueError(
                "parent compressed external records are missing derived targets: "
                + ", ".join(missing_records[:10])
            )
        derived_compressed_payload = {
            **compressed_payload,
            "records": [parent_records[acpt_no] for acpt_no in child_acpt_numbers],
        }
        if child_acpt_numbers:
            _targets, _ = _collect_internal_targets_from_compressed_payload(
                derived_compressed_payload
            )
        resolved_output_directory = Path(output_directory).expanduser().resolve()
        expected_output_directory = workspace.internal_owner_mode(
            mode, parent_mode=parent_mode
        ).resolve()
        if resolved_output_directory != expected_output_directory:
            raise ValueError(
                "derived filter internal HTML must use its parent-owned directory: "
                f"{expected_output_directory}"
            )
        saved_paths, integrity = _strictly_reuse_parent_html(
            output_directory=resolved_output_directory,
            acpt_numbers=child_acpt_numbers,
            source_json=derived_compressed_payload,
        )
        verification = _verify_internal_download_membership(
            expected_acpt_numbers=child_acpt_numbers,
            saved_paths=saved_paths,
            allow_missing=False,
        )
        verification["hash_verified_target_html_count"] = integrity[
            "hash_verified_target_html_count"
        ]
        return {
            "format": "kind_disclosure_internal_html_download_v1",
            "mode": mode,
            "parent_mode": parent_mode,
            "reused_parent_html": True,
            "network_fetch_count": 0,
            "output_directory": str(resolved_output_directory),
            "requested_count": len(child_acpt_numbers),
            "saved_count": len(saved_paths),
            "cancelled": False,
            "acpt_numbers": child_acpt_numbers,
            "saved_files": [str(path) for path in saved_paths],
            "manifest_path": str(
                resolved_output_directory / HTML_MANIFEST_FILENAME
            ),
            "verification": verification,
            "progress_log": [
                f"부모 필터 {parent_mode}의 내부 HTML "
                f"{len(saved_paths)}건을 재사용했습니다."
            ],
        }
    targets, source_json = _collect_internal_targets_from_compressed_payload(
        compressed_payload
    )

    targets = _apply_limit_to_targets(targets, body.get("limit"))
    acpt_numbers = [target["acpt_no"] for target in targets]
    target_years = {
        target["acpt_no"]: target["year"]
        for target in targets
    }
    cancel_token = str(body.get("cancel_token") or "").strip() or None
    _clear_cancel_token(cancel_token)

    resolved_output_directory = Path(output_directory).expanduser().resolve()
    progress_interval = _parse_progress_interval(body.get("progress_interval"))
    max_workers = resolve_worker_count(
        body.get("max_workers"),
        item_count=len(targets),
        field_name="max_workers",
    )
    progress_log: deque[str] = deque(maxlen=100)
    processed_count = 0
    progress_lock = Lock()

    def emit(message: str) -> None:
        with progress_lock:
            progress_log.append(message)
            if progress_callback is not None:
                progress_callback(message)

    def handle_progress(message: str) -> None:
        nonlocal processed_count
        if message.startswith(
            ("Saved KIND internal HTML ", "Skipping existing KIND internal HTML")
        ):
            with progress_lock:
                processed_count += 1
                current_count = processed_count
            emit(message)
            if current_count % progress_interval == 0:
                emit(
                    f"HTML 내부 저장 중간 확인: {current_count}/{len(acpt_numbers)}건 처리."
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
    emit(f"병렬 처리: {max_workers}개 워커")
    existing_paths_by_acpt_no: dict[str, Path] = {}
    source_integrity_by_acpt_no: dict[str, dict[str, Any]] = {}
    download_acpt_numbers = acpt_numbers
    if bool(body.get("skip_existing", True)):
        existing_check_started_at = time.monotonic()
        emit("기존 HTML 구조 및 기준 해시 검사를 시작합니다.")
        output_summary = _validate_html_output_directory_files(
            resolved_output_directory,
            acpt_numbers,
            target_years=target_years,
            collect_integrity=True,
            problem_file_limit=body.get("problem_file_limit"),
        )
        actual_integrity_by_acpt_no = output_summary.pop(
            "_target_integrity_by_acpt_no"
        )
        integrity_summary = _inspect_html_integrity(
            resolved_output_directory,
            acpt_numbers,
            source_json=source_json,
            structurally_valid_acpt_numbers=output_summary[
                "existing_target_acpt_numbers"
            ],
            actual_integrity_by_acpt_no=actual_integrity_by_acpt_no,
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
        emit(
            "저장 디렉토리 검사 완료: 대상 HTML/메타데이터 외 파일 없음 · "
            f"{time.monotonic() - existing_check_started_at:.1f}초."
        )
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
            timeout = float(body.get("timeout") or 20.0)
            wait_seconds = float(body.get("wait_seconds") or 0.0)
            max_requests_per_minute = int(
                body.get("max_requests_per_minute") or 90
            )
            if timeout <= 0:
                raise ValueError("timeout must be > 0")
            if wait_seconds < 0:
                raise ValueError("wait_seconds_between_requests must be >= 0")
            if (
                max_requests_per_minute < 1
                or max_requests_per_minute > 100
            ):
                raise ValueError(
                    "max_requests_per_minute must be between 1 and 100"
                )
            spacing_limiter = RequestSpacingLimiter(
                max(wait_seconds, 60.0 / max_requests_per_minute)
            )
            target_by_acpt_no = {target["acpt_no"]: target for target in targets}
            download_targets = [
                target_by_acpt_no[acpt_no] for acpt_no in download_acpt_numbers
            ]
            downloaded_paths.extend(
                download_disclosure_internal_htmls(
                    output_directory=resolved_output_directory,
                    request_headers=DEFAULT_REQUEST_HEADERS,
                    targets=[
                        {"acpt_no": target["acpt_no"], "doc_no": target["doc_no"]}
                        for target in download_targets
                    ],
                    timeout=timeout,
                    wait_seconds_between_requests=wait_seconds,
                    max_requests_per_minute=max_requests_per_minute,
                    skip_existing=False,
                    progress_callback=handle_progress,
                    cancel_check=lambda: _is_cancelled(cancel_token)
                    or bool(cancel_check and cancel_check()),
                    max_workers=max_workers,
                    spacing_limiter=spacing_limiter,
                    kind_proxy_urls=body.get("kind_proxy_urls"),
                    target_output_directories={
                        target["acpt_no"]: (
                            resolved_output_directory
                            / target_years[target["acpt_no"]]
                        )
                        for target in download_targets
                    },
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
        hash_started_at = time.monotonic()
        emit(f"새 HTML 기준 해시 생성을 시작합니다: {len(downloaded_paths)}건.")
        downloaded_integrity, hash_cancelled = _hash_html_files(
            {path.stem: path for path in downloaded_paths},
            progress_callback=emit,
            cancel_check=lambda: _is_cancelled(cancel_token)
            or bool(cancel_check and cancel_check()),
        )
        cancelled = (
            cancelled
            or hash_cancelled
            or _is_cancelled(cancel_token)
            or bool(cancel_check and cancel_check())
        )
        if cancelled:
            emit(
                "새 HTML 기준 해시 생성을 중지했습니다: "
                f"{time.monotonic() - hash_started_at:.1f}초."
            )
        else:
            emit(
                f"새 HTML 기준 해시 생성 완료: {len(downloaded_integrity)}건 · "
                f"{time.monotonic() - hash_started_at:.1f}초."
            )
            source_integrity_by_acpt_no.update(downloaded_integrity)
    finally:
        _clear_cancel_token(cancel_token)
    saved_acpt_numbers = [path.stem for path in saved_paths]
    manifest_path = None
    if not cancelled:
        manifest_path = _write_html_manifest(
            output_directory=resolved_output_directory,
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
        "manifest_path": str(manifest_path) if manifest_path is not None else "",
        "verification": verification,
        "progress_log": list(progress_log),
    }
