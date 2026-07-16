"""KIND download folder inspection helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from finiq.data_scraper.workflow import inspect_download_directory_pages

from finiq.market_desk.web.features.downloads.kind_common import *

def inspect_download_output_directory_payload(
    payload: dict[str, Any],
    progress_callback: Any | None = None,
    cancel_check: Any | None = None,
) -> dict[str, Any]:
    """Report or delete existing download files that would block a clean run."""

    def log(message: str) -> None:
        if progress_callback is not None:
            progress_callback(message)

    def check_cancel() -> None:
        if cancel_check is not None and cancel_check():
            raise DownloadCancelled("Folder inspection cancelled by the user")

    log("기존 다운로드 파일 구조를 검사하는 중...")
    base, targets = _download_cleanup_targets(payload)
    dry_run = bool(payload.get("dry_run", False))

    candidates_by_path: dict[str, dict[str, str]] = {}
    precomputed_statuses: dict[str, dict[str, int]] = {}

    log("연도별 대상 폴더 수집 중...")
    for folder, page_size in targets:
        check_cancel()
        if not folder.exists():
            continue
        body_files = _result_body_files(folder)
        if not body_files:
            continue

        input_snapshot = _require_current_download_input_snapshot(folder)

        saved_filters = _snapshot_filters_payload(input_snapshot)
        has_current_filters = {
            "company_name",
            "submitter_name",
            "market_label",
            "securities_label",
            "disclosure_type_groups",
            "last_report_only",
        }.issubset(payload)
        if has_current_filters and not _filters_payloads_match(
            _current_filters_payload(payload), saved_filters
        ):
            raise ValueError(
                f"{folder.name}: 기존 메타데이터의 검색 설정이 현재 검색 설정과 다릅니다. "
                "기존 메타데이터 기준으로 설정을 맞춘 뒤 다시 실행하세요."
            )

        locked_page_size = input_snapshot.get("page_size")
        if locked_page_size is None or int(locked_page_size) != page_size:
            reason = "현재 요청의 페이지 크기와 맞지 않는 기존 다운로드 상태"
            for path in body_files + _workflow_auxiliary_files(folder):
                candidates_by_path[str(path)] = _relative_candidate(path, base, reason)
            continue
        try:
            precomputed_statuses[str(folder)] = inspect_download_directory_pages(
                folder,
                expected_page_size=page_size,
                require_complete=False,
                validation_parallelism=1,
            )
        except (OSError, ValueError) as exc:
            reason = str(exc)
            for path in body_files + _workflow_auxiliary_files(folder):
                candidates_by_path[str(path)] = _relative_candidate(path, base, reason)

    log("연도별 폴더 무결성 검사 완료.")

    deletion_candidates = sorted(
        candidates_by_path.values(), key=lambda item: item["name"]
    )
    if deletion_candidates and not dry_run:
        check_cancel()
        confirmed = (
            payload.get("delete_confirmed") is True
            and str(payload.get("delete_confirmation_text") or "").strip()
            == DOWNLOAD_DELETE_CONFIRMATION_TEXT
        )
        if not confirmed:
            msg = f'파일 삭제 전 "{DOWNLOAD_DELETE_CONFIRMATION_TEXT}" 입력과 삭제 허가가 필요합니다.'
            raise ValueError(msg)
        log(f"삭제 예정 파일 {len(deletion_candidates)}개 삭제 중...")
        for candidate in deletion_candidates:
            check_cancel()
            Path(candidate["path"]).unlink(missing_ok=True)
        log("파일 삭제 완료.")

    log("폴더 검증 요약 데이터 구성 중...")
    statuses = [
        _download_integrity_status(
            folder, page_size, precomputed_statuses.get(str(folder))
        )
        for folder, page_size in targets
        if folder.exists()
    ]
    downloaded_pages = sum(
        int(status.get("downloaded_pages") or 0) for status in statuses
    )
    total_pages = sum(int(status.get("total_pages") or 0) for status in statuses)
    log("폴더 구조 검사 완료.")
    return {
        "format": "kind_download_folder_cleanup_v1",
        "output_directory": str(base),
        "split_by_year": str(payload.get("mode") or "single").strip().lower()
        == "yearly",
        "dry_run": dry_run,
        "deleted_count": 0 if dry_run else len(deletion_candidates),
        "deletion_candidate_count": len(deletion_candidates),
        "deletion_candidates": deletion_candidates,
        "deleted_files": [] if dry_run else deletion_candidates,
        "requested_count": total_pages,
        "download_statuses": statuses,
        "summary": {
            "success": downloaded_pages,
            "failed": max(total_pages - downloaded_pages, 0),
            "total": total_pages,
        },
        "download_needed_count": 0,
        "download_needed_pages": 0,
    }
