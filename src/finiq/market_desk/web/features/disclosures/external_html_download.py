"""Disclosure external HTML download payload helpers."""

from __future__ import annotations

from finiq.market_desk.web.features.disclosures.html_common import *

def download_disclosure_external_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Download KIND external HTML files for receipt numbers found in the request JSON."""
    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        msg = "output_directory is required"
        raise ValueError(msg)

    source_json, resolved_source_json_path = _load_workspace_filtered_payload(body)

    acpt_numbers = collect_acpt_numbers_from_json(source_json)
    if not acpt_numbers:
        msg = "No acpt_no values found in JSON"
        raise ValueError(msg)

    acpt_numbers = _apply_limit_to_acpt_numbers(acpt_numbers, body.get("limit"))
    target_years = _target_years_from_json(source_json, acpt_numbers)

    cancel_token = str(body.get("cancel_token") or "").strip() or None
    _clear_cancel_token(cancel_token)

    resolved_output_directory = Path(output_directory).expanduser().resolve()
    progress_interval = _parse_progress_interval(body.get("progress_interval"))
    max_workers = resolve_worker_count(
        body.get("max_workers"),
        item_count=len(acpt_numbers),
        field_name="max_workers",
    )
    progress_log: list[str] = []
    processed_count = 0

    def emit(message: str) -> None:
        progress_log.append(message)
        if progress_callback is not None:
            progress_callback(message)

    def handle_progress(message: str) -> None:
        nonlocal processed_count
        if message.startswith(
            ("Saved KIND external HTML ", "Skipping existing KIND external HTML")
        ):
            processed_count += 1
            if processed_count % progress_interval == 0:
                emit(
                    f"HTML 저장 중간 확인: {processed_count}/{len(acpt_numbers)}건 처리."
                )
            return
        if message.startswith("Fetching KIND external HTML "):
            return
        emit(message)

    emit(f"HTML 저장 대상 접수번호 {len(acpt_numbers)}건을 준비했습니다.")
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
            source_json_path=resolved_source_json_path,
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
                f"기준 해시가 없는 기존 외부 HTML이 {len(unverified_acpt_numbers)}건 있습니다. "
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
            handle_progress(f"Skipping existing KIND external HTML: {path}")
    try:
        downloaded_paths = []
        raw_max_retries = body.get("max_retries")
        if raw_max_retries is None or raw_max_retries == "":
            max_retries = 5
        else:
            max_retries = int(raw_max_retries)
        if download_acpt_numbers:
            grouped_acpt_numbers: dict[str, list[str]] = {}
            for acpt_no in download_acpt_numbers:
                grouped_acpt_numbers.setdefault(target_years[acpt_no], []).append(
                    acpt_no
                )
            for year, group_acpt_numbers in grouped_acpt_numbers.items():
                downloaded_paths.extend(
                    download_disclosure_external_htmls(
                        output_directory=resolved_output_directory / year,
                        request_headers=DEFAULT_REQUEST_HEADERS,
                        acpt_numbers=group_acpt_numbers,
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
                        max_workers=max_workers,
                        max_retries=max_retries,
                    )
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
        cancelled = _is_cancelled(cancel_token) or bool(cancel_check and cancel_check())
    finally:
        _clear_cancel_token(cancel_token)
    saved_acpt_numbers = [path.stem for path in saved_paths]
    missing_acpt_numbers = [
        acpt_no for acpt_no in acpt_numbers if acpt_no not in saved_paths_by_acpt_no
    ]
    manifest_path = _write_html_manifest(
        output_directory=resolved_output_directory,
        source_json_path=resolved_source_json_path,
        acpt_numbers=saved_acpt_numbers,
        source_json=source_json,
        source_integrity=source_integrity_by_acpt_no,
    )
    emit(f"HTML 메타데이터 저장 완료: {manifest_path}")
    emit(
        f"HTML 저장 {'중지' if cancelled else '완료'}: 저장 파일 {len(saved_paths)}/{len(acpt_numbers)}건."
    )
    return {
        "format": "kind_disclosure_external_html_download_v1",
        "mode": validate_workspace_mode(body.get("mode")),
        "output_directory": str(resolved_output_directory),
        "requested_count": len(acpt_numbers),
        "saved_count": len(saved_paths),
        "cancelled": cancelled,
        "acpt_numbers": acpt_numbers,
        "missing_acpt_numbers": missing_acpt_numbers,
        "saved_files": [str(path) for path in saved_paths],
        "manifest_path": str(manifest_path),
        "progress_log": progress_log[-100:],
    }
