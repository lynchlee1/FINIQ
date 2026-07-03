"""KIND download folder inspection helpers."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any

from finiq.data_scraper.workflow import inspect_download_directory_pages, validate_downloaded_result_page
from finiq.data_scraper.workflow.workflow import _validate_downloaded_result_page_task

from finiq.market_desk.web.features.downloads.kind_common import *
from finiq.market_desk.web.features.downloads import kind_existing

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

    files_to_validate: list[tuple[Path, int]] = []
    candidates_by_path: dict[str, dict[str, str]] = {}
    folder_body_files: dict[Path, list[Path]] = {}
    candidate_repair_snapshots: dict[Path, dict[str, Any]] = {}

    log("연도별 대상 폴더 수집 중...")
    for folder, page_size in targets:
        check_cancel()
        if not folder.exists():
            continue
        body_files = _result_body_files(folder)
        if not body_files:
            continue

        folder_body_files[folder] = body_files

        try:
            input_snapshot = _load_workflow_input(folder)
        except Exception:
            input_snapshot = None
        if _is_trusted_download_input_snapshot(input_snapshot):
            saved_filters = _snapshot_filters_payload(input_snapshot or {})
            if _has_complete_current_download_payload(
                payload
            ) and not _filters_payloads_match(
                _current_filters_payload(payload),
                saved_filters,
            ):
                raise ValueError(
                    f"{folder.name}: 기존 메타데이터의 검색 설정이 현재 검색 설정과 다릅니다. "
                    "기존 메타데이터 기준으로 설정을 맞춘 뒤 다시 실행하세요."
                )
        else:
            if not _has_complete_current_download_payload(payload):
                if (
                    isinstance(input_snapshot, dict)
                    and input_snapshot.get("page_size") is not None
                ):
                    input_snapshot = {
                        **input_snapshot,
                        "page_size": input_snapshot.get("page_size"),
                    }
                    log(
                        f"{folder.name}: 신뢰할 수 없는 메타데이터지만 로컬 무결성 검사만 진행합니다."
                    )
                    locked_page_size = input_snapshot.get("page_size")
                    if locked_page_size is None or int(locked_page_size) != page_size:
                        reason = (
                            "현재 요청의 페이지 크기와 맞지 않는 기존 다운로드 상태"
                        )
                        for path in body_files + _workflow_auxiliary_files(folder):
                            candidates_by_path[str(path)] = _relative_candidate(
                                path, base, reason
                            )
                        continue
                    for path in body_files:
                        files_to_validate.append((path, page_size))
                    continue
                else:
                    for path in body_files:
                        candidates_by_path[str(path)] = _relative_candidate(
                            path, base, "입력 스냅샷 없이 남아 있는 다운로드 결과"
                        )
                    continue

            expected_start, expected_end = _expected_date_range_for_folder(
                payload, folder
            )
            evidence_range = _folder_date_range_from_name(
                folder
            ) or kind_existing._infer_date_range_from_disclosures(folder)
            if evidence_range is not None and evidence_range != (
                expected_start,
                expected_end,
            ):
                reason = (
                    "현재 검색 설정의 날짜 범위와 맞지 않는 기존 다운로드 결과 "
                    f"({evidence_range[0].isoformat()}~{evidence_range[1].isoformat()})"
                )
                for path in body_files:
                    candidates_by_path[str(path)] = _relative_candidate(
                        path, base, reason
                    )
                continue

            input_snapshot = _download_input_snapshot_from_payload(
                payload,
                start=expected_start,
                end=expected_end,
                page_size=page_size,
            )
            candidate_repair_snapshots[folder] = input_snapshot
            log(f"{folder.name}: 메타데이터가 없어 현재 검색 설정 기준으로 검사합니다.")

        locked_page_size = input_snapshot.get("page_size")
        if locked_page_size is None or int(locked_page_size) != page_size:
            reason = "현재 요청의 페이지 크기와 맞지 않는 기존 다운로드 상태"
            for path in body_files + _workflow_auxiliary_files(folder):
                candidates_by_path[str(path)] = _relative_candidate(path, base, reason)
            continue

        for path in body_files:
            files_to_validate.append((path, page_size))

    total_files = len(files_to_validate)
    log(f"검증 대상 파일 {total_files}개 수집 완료. 1패스 병렬 무결성 검사 시작...")

    page_infos: dict[str, dict[str, int]] = {}
    if files_to_validate:
        worker_count = min(os.cpu_count() or 1, total_files)
        executor = None
        is_cancelled = False
        try:
            executor = ProcessPoolExecutor(max_workers=worker_count)
            future_to_path = {
                executor.submit(
                    _validate_downloaded_result_page_task, (str(path), page_size)
                ): path
                for path, page_size in files_to_validate
            }
            completed_count = 0
            for future in as_completed(future_to_path):
                if cancel_check is not None and cancel_check():
                    is_cancelled = True
                    for fut in future_to_path:
                        fut.cancel()
                    try:
                        executor.shutdown(wait=False, cancel_futures=True)
                    except TypeError:
                        executor.shutdown(wait=False)
                    raise DownloadCancelled("Folder inspection cancelled by the user")
                path = future_to_path[future]
                try:
                    page_infos[str(path)] = future.result()
                except BrokenProcessPool:
                    raise
                except Exception as exc:
                    candidates_by_path[str(path)] = _relative_candidate(
                        path, base, str(exc)
                    )
                completed_count += 1
                if completed_count % 500 == 0 or completed_count == total_files:
                    log(f"파일 무결성 검증 중... ({completed_count}/{total_files})")
        except (BrokenProcessPool, OSError, PermissionError, RuntimeError):
            if is_cancelled:
                raise
            log("멀티프로세싱 검증 실패로 인해 싱글스레드 순차 검증으로 전환합니다...")
            for path, page_size in files_to_validate:
                check_cancel()
                try:
                    page_infos[str(path)] = validate_downloaded_result_page(
                        path, expected_page_size=page_size
                    )
                except Exception as exc:
                    candidates_by_path[str(path)] = _relative_candidate(
                        path, base, str(exc)
                    )
        finally:
            if executor is not None and not is_cancelled:
                try:
                    executor.shutdown(wait=True, cancel_futures=False)
                except TypeError:
                    executor.shutdown(wait=True)

    log("폴더 간 페이지 번호 연속성 및 메타데이터 일관성 검사 중...")
    precomputed_statuses: dict[str, dict[str, int]] = {}
    download_needed_count = 0
    download_needed_pages = 0
    for folder, page_size in targets:
        check_cancel()
        if folder not in folder_body_files:
            continue
        body_files = folder_body_files[folder]

        folder_candidates = [
            path for path in body_files if str(path) in candidates_by_path
        ]
        if folder_candidates:
            continue

        folder_page_infos = {}
        for path in body_files:
            info = page_infos.get(str(path))
            if info is not None:
                folder_page_infos[path] = info

        if len(folder_page_infos) != len(body_files):
            continue

        page_numbers = set()
        total_pages_values = set()
        total_items_values = set()
        for path, info in folder_page_infos.items():
            current_page = int(info["current_page"])
            if current_page in page_numbers:
                for p in body_files:
                    candidates_by_path[str(p)] = _relative_candidate(
                        p, base, f"중복되는 페이지 번호 {current_page}"
                    )
                break
            page_numbers.add(current_page)
            total_pages_values.add(int(info["total_pages"]))
            total_items_values.add(int(info["total_items"]))
        else:
            if len(total_pages_values) != 1 or len(total_items_values) != 1:
                reason = "페이지들 사이의 전체 페이지 수 또는 건수가 다릅니다."
                for p in body_files:
                    candidates_by_path[str(p)] = _relative_candidate(p, base, reason)
            else:
                downloaded_pages = len(body_files)
                total_pages = next(iter(total_pages_values))
                total_items = next(iter(total_items_values))
                expected_prefix = set(range(1, downloaded_pages + 1))
                if page_numbers != expected_prefix:
                    reason = f"페이지 번호가 1부터 연속적이지 않습니다: {sorted(page_numbers)}"
                    for p in body_files:
                        candidates_by_path[str(p)] = _relative_candidate(
                            p, base, reason
                        )
                else:
                    precomputed_statuses[str(folder)] = {
                        "downloaded_pages": downloaded_pages,
                        "total_pages": total_pages,
                        "total_items": total_items,
                    }
                    repair_snapshot = candidate_repair_snapshots.get(folder)
                    if repair_snapshot is not None:
                        log(f"{folder.name}: KIND 현재 건수 대조 중...")
                        kind_count = kind_existing.get_current_kind_total_count(
                            repair_snapshot
                        )
                        if kind_count is None:
                            reason = "KIND 현재 건수를 확인할 수 없어 메타데이터를 자동 복구할 수 없습니다."
                            for p in body_files:
                                candidates_by_path[str(p)] = _relative_candidate(
                                    p, base, reason
                                )
                            precomputed_statuses.pop(str(folder), None)
                        elif total_items > kind_count:
                            reason = f"현재 검색 설정의 KIND 건수({kind_count})보다 로컬 건수({total_items})가 많습니다."
                            for p in body_files:
                                candidates_by_path[str(p)] = _relative_candidate(
                                    p, base, reason
                                )
                            precomputed_statuses.pop(str(folder), None)
                        else:
                            if total_items < kind_count:
                                download_needed_count += kind_count - total_items
                                expected_pages = (
                                    kind_count + page_size - 1
                                ) // page_size
                                download_needed_pages += max(
                                    expected_pages - total_pages, 0
                                )
                                log(
                                    f"{folder.name}: 현재 설정 기준 추가 다운로드 필요 "
                                    f"{kind_count - total_items}건"
                                )
                            _write_download_input_snapshot(folder, repair_snapshot)
                            log(
                                f"{folder.name}: 현재 검색 설정으로 메타데이터를 자동 작성했습니다."
                            )

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
        "download_needed_count": download_needed_count,
        "download_needed_pages": download_needed_pages,
    }

