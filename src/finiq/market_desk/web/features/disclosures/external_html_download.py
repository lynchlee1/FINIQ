"""Disclosure external HTML download payload helpers."""

from __future__ import annotations

import time
from collections import deque

from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
)
from finiq.market_desk.web.features.disclosures.html_cleanup import (
    inspect_all_disclosure_external_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_common import *


def redownload_missing_disclosure_external_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Repair owner-mode HTML identified by the all-mode inspection."""
    data_root = str(body.get("data_root") or "").strip()
    if not data_root:
        raise ValueError("data_root is required")

    inspection = inspect_all_disclosure_external_html_payload(body)
    targets = [
        result
        for result in inspection["results"]
        if not result.get("parent_mode")
        and (
            int(result.get("download_required_target_html_count") or 0)
            + int(result.get("hash_unverified_target_html_count") or 0)
        )
        > 0
    ]
    results: list[dict[str, Any]] = []
    cancelled = False
    setting_keys = (
        "timeout",
        "max_requests_per_minute",
        "wait_seconds",
        "skip_existing",
        "progress_interval",
        "problem_file_limit",
        "max_workers",
        "kind_proxy_urls",
    )
    for index, target in enumerate(targets, start=1):
        if cancel_check is not None and cancel_check():
            cancelled = True
            break
        mode = target["mode"]
        if progress_callback is not None:
            progress_callback(f"재다운로드 {index}/{len(targets)}: {mode}")
        payload = apply_workspace_defaults(
            "external_html_download",
            {
                "data_root": data_root,
                "mode": mode,
                **{key: body.get(key) for key in setting_keys if key in body},
            },
        )
        try:
            result = download_disclosure_external_html_payload(
                payload,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
                redownload_unverified_existing=True,
            )
            cancelled = bool(result.get("cancelled"))
            results.append({"mode": mode, "passed": not cancelled, **result})
            if cancelled:
                break
        except Exception as exc:
            results.append({"mode": mode, "passed": False, "error": str(exc)})

    failed_modes = [result["mode"] for result in results if not result["passed"]]
    verification = inspect_all_disclosure_external_html_payload(body)
    return {
        "format": "finiq_disclosure_external_html_redownload_result_v1",
        "passed": not cancelled and not failed_modes and verification["passed"],
        "cancelled": cancelled,
        "target_mode_count": len(targets),
        "completed_mode_count": len(results) - len(failed_modes),
        "failed_mode_count": len(failed_modes),
        "failed_modes": failed_modes,
        "results": results,
        "verification": verification,
    }

def download_disclosure_external_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
    *,
    redownload_unverified_existing: bool = False,
) -> dict[str, Any]:
    """Download KIND external HTML files for receipt numbers found in the request JSON."""
    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        msg = "output_directory is required"
        raise ValueError(msg)

    source_json, _source_json_path = _load_workspace_filtered_payload(body)

    acpt_numbers = collect_acpt_numbers_from_json(source_json)
    parent_mode_raw = body.get("parent_mode")
    if not acpt_numbers and parent_mode_raw in (None, ""):
        msg = "No acpt_no values found in JSON"
        raise ValueError(msg)

    acpt_numbers = _apply_limit_to_acpt_numbers(acpt_numbers, body.get("limit"))
    target_years = _target_years_from_json(source_json, acpt_numbers)

    cancel_token = str(body.get("cancel_token") or "").strip() or None
    _clear_cancel_token(cancel_token)

    resolved_output_directory = Path(output_directory).expanduser().resolve()
    if parent_mode_raw not in (None, ""):
        workspace = resolve_disclosure_workspace(body.get("data_root") or "")
        mode = validate_workspace_mode(body.get("mode"))
        parent_mode = validate_workspace_mode(parent_mode_raw)
        expected_output_directory = workspace.external_owner_mode(
            mode, parent_mode=parent_mode
        ).resolve()
        if resolved_output_directory != expected_output_directory:
            raise ValueError(
                "derived filter external HTML must use its parent-owned directory: "
                f"{expected_output_directory}"
            )
        saved_paths, verification = _strictly_reuse_parent_html(
            output_directory=resolved_output_directory,
            acpt_numbers=acpt_numbers,
            source_json=source_json,
        )
        return {
            "format": "kind_disclosure_external_html_download_v1",
            "mode": mode,
            "parent_mode": parent_mode,
            "reused_parent_html": True,
            "network_fetch_count": 0,
            "output_directory": str(resolved_output_directory),
            "requested_count": len(acpt_numbers),
            "saved_count": len(saved_paths),
            "cancelled": False,
            "acpt_numbers": acpt_numbers,
            "missing_acpt_numbers": [],
            "saved_files": [str(path) for path in saved_paths],
            "manifest_path": str(
                resolved_output_directory / HTML_MANIFEST_FILENAME
            ),
            "verification": verification,
            "progress_log": [
                f"부모 필터 {parent_mode}의 외부 HTML "
                f"{len(saved_paths)}건을 재사용했습니다."
            ],
        }
    progress_interval = _parse_progress_interval(body.get("progress_interval"))
    max_workers = resolve_worker_count(
        body.get("max_workers"),
        item_count=len(acpt_numbers),
        field_name="max_workers",
    )
    progress_log: deque[str] = deque(maxlen=100)
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
            emit(message)
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
        if unverified_acpt_numbers and not redownload_unverified_existing:
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
        if redownload_unverified_existing:
            download_targets.update(unverified_acpt_numbers)
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
            handle_progress(f"Skipping existing KIND external HTML: {path}")
    try:
        downloaded_paths = []
        raw_max_retries = body.get("max_retries")
        if raw_max_retries is None or raw_max_retries == "":
            max_retries = 5
        else:
            max_retries = int(raw_max_retries)
        if download_acpt_numbers:
            downloaded_paths.extend(
                download_disclosure_external_htmls(
                    output_directory=resolved_output_directory,
                    request_headers=DEFAULT_REQUEST_HEADERS,
                    acpt_numbers=download_acpt_numbers,
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
                    kind_proxy_urls=body.get("kind_proxy_urls"),
                    target_output_directories={
                        acpt_no: resolved_output_directory / target_years[acpt_no]
                        for acpt_no in download_acpt_numbers
                    },
                )
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
        downloaded_integrity, _ = _hash_html_files(
            {path.stem: path for path in downloaded_paths},
            progress_callback=emit,
            cancel_check=cancel_check,
        )
        emit(
            f"새 HTML 기준 해시 생성 완료: {len(downloaded_integrity)}건 · "
            f"{time.monotonic() - hash_started_at:.1f}초."
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
        "progress_log": list(progress_log),
    }
