"""KIND download folder inspection helpers."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from finiq.data_scraper.workflow import inspect_download_directory_pages

from finiq.market_desk.web.features.downloads.kind_common import *


def _deletion_confirmation(
    payload: dict[str, Any],
    base: Path,
    candidates: list[dict[str, str]],
) -> tuple[str, list[tuple[Path, dict[str, Any]]]]:
    validated: list[tuple[Path, dict[str, Any]]] = []
    for candidate in candidates:
        path = Path(candidate["path"])
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"삭제 후보가 일반 파일이 아닙니다: {candidate['name']}")
        resolved = path.resolve(strict=True)
        try:
            relative_name = resolved.relative_to(base).as_posix()
        except ValueError as exc:
            raise ValueError(
                f"삭제 후보가 데이터 경로 밖에 있습니다: {candidate['name']}"
            ) from exc
        file_stat = resolved.stat()
        descriptor = {
            "name": relative_name,
            "reason": candidate["reason"],
            "size": file_stat.st_size,
            "mtime_ns": file_stat.st_mtime_ns,
        }
        validated.append((resolved, descriptor))
    confirmation_payload = {
        "input_fingerprint": _download_inspection_input_fingerprint(payload),
        "candidates": [descriptor for _path, descriptor in validated],
    }
    encoded = json.dumps(
        confirmation_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), validated


def _delete_candidates_as_batch(
    base: Path,
    validated_candidates: list[tuple[Path, dict[str, Any]]],
) -> str | None:
    quarantine = Path(
        tempfile.mkdtemp(prefix=".finiq-kind-delete-", dir=base.parent)
    )
    moved: list[tuple[Path, Path]] = []
    try:
        for source, descriptor in validated_candidates:
            if source.is_symlink() or not source.is_file():
                raise ValueError(f"삭제 후보가 일반 파일이 아닙니다: {descriptor['name']}")
            current_stat = source.stat()
            if (
                current_stat.st_size != descriptor["size"]
                or current_stat.st_mtime_ns != descriptor["mtime_ns"]
            ):
                raise ValueError(
                    f"삭제 후보가 검사 후 변경되었습니다: {descriptor['name']}"
                )
            target = quarantine / descriptor["name"]
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(source, target)
            moved.append((source, target))
    except Exception as exc:
        rollback_errors: list[str] = []
        for source, target in reversed(moved):
            try:
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, source)
            except Exception as rollback_exc:  # pragma: no cover - OS failure path
                rollback_errors.append(str(rollback_exc))
        shutil.rmtree(quarantine, ignore_errors=True)
        detail = f"삭제 후보 격리에 실패해 원래 위치로 되돌렸습니다: {exc}"
        if rollback_errors:
            detail += " 되돌리기 오류: " + "; ".join(rollback_errors)
        raise ValueError(detail) from exc

    try:
        shutil.rmtree(quarantine)
    except OSError as exc:  # pragma: no cover - OS failure path
        return f"격리된 삭제 파일 정리에 실패했습니다: {quarantine} ({exc})"
    return None


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
    yearly_mode = str(payload.get("mode") or "single").strip().lower() == "yearly"
    validation_parallelism = _as_worker_count(payload)

    candidates_by_path: dict[str, dict[str, str]] = {}
    precomputed_statuses: dict[str, dict[str, int]] = {}
    precomputed_file_states: dict[str, str] = {}
    validation_targets: list[tuple[int, Path, int]] = []

    log(f"검사 대상 저장 폴더: {len(targets)}개.")
    log(f"저장 파일 병렬 검사: {validation_parallelism}개 워커.")
    for index, (folder, page_size) in enumerate(targets, start=1):
        check_cancel()
        log(
            f"저장 파일 구성 검사: {index}/{len(targets)}개 폴더 "
            f"({folder.name})."
        )
        if not folder.exists():
            log(f"저장 파일 구성 검사 건너뜀: {folder.name} 폴더가 없습니다.")
            continue
        body_files = _result_body_files(folder)
        if not body_files:
            log(f"저장 파일 구성 검사 건너뜀: {folder.name}에 저장 파일이 없습니다.")
            continue

        input_snapshot = _require_current_download_input_snapshot(folder)

        expected_folder_name = (
            f"{str(input_snapshot['start_date']).replace('-', '')}_"
            f"{str(input_snapshot['end_date']).replace('-', '')}"
        )
        if yearly_mode and folder.name != expected_folder_name:
            reason = (
                f"폴더 기간 {folder.name}과 메타데이터 기간 "
                f"{input_snapshot['start_date']}~{input_snapshot['end_date']}이 다릅니다."
            )
            for path in body_files + _workflow_auxiliary_files(folder):
                candidates_by_path[str(path)] = _relative_candidate(path, base, reason)
            log(
                f"저장 파일 구성 검사 완료: {index}/{len(targets)}개 폴더 "
                f"({folder.name})."
            )
            continue

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
            log(
                f"저장 파일 구성 검사 완료: {index}/{len(targets)}개 폴더 "
                f"({folder.name})."
            )
            continue
        validation_targets.append((index, folder, page_size))

    folder_workers = min(validation_parallelism, max(1, len(validation_targets)))
    page_workers = validation_parallelism if len(validation_targets) == 1 else 1

    def inspect_target(
        target: tuple[int, Path, int],
    ) -> tuple[
        int,
        Path,
        dict[str, int] | None,
        str | None,
        str | None,
    ]:
        index, folder, page_size = target
        check_cancel()
        try:
            file_state_before = _result_body_file_state(folder)
            status = inspect_download_directory_pages(
                folder,
                expected_page_size=page_size,
                require_complete=False,
                validation_parallelism=page_workers,
            )
            file_state_after = _result_body_file_state(folder)
        except (OSError, ValueError) as exc:
            return index, folder, None, None, str(exc)
        stable_file_state = (
            file_state_after if file_state_before == file_state_after else None
        )
        return index, folder, status, stable_file_state, None

    if folder_workers == 1:
        validation_results = map(inspect_target, validation_targets)
    else:
        executor = ThreadPoolExecutor(
            max_workers=folder_workers,
            thread_name_prefix="kind-folder-inspection",
        )
        validation_results = executor.map(inspect_target, validation_targets)

    try:
        for index, folder, status, file_state, error in validation_results:
            check_cancel()
            if status is not None:
                precomputed_statuses[str(folder)] = status
            if file_state is not None:
                precomputed_file_states[str(folder)] = file_state
            if error is not None:
                for path in _result_body_files(folder) + _workflow_auxiliary_files(folder):
                    candidates_by_path[str(path)] = _relative_candidate(
                        path, base, error
                    )
            log(
                f"저장 파일 구성 검사 완료: {index}/{len(targets)}개 폴더 "
                f"({folder.name})."
            )
    finally:
        if folder_workers > 1:
            executor.shutdown()

    log("연도별 폴더 무결성 검사 완료.")

    deletion_candidates = sorted(
        candidates_by_path.values(), key=lambda item: item["name"]
    )
    deletion_confirmation, validated_candidates = _deletion_confirmation(
        payload,
        base,
        deletion_candidates,
    )
    deletion_cleanup_warning: str | None = None
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
        provided_confirmation = str(
            payload.get("deletion_confirmation") or ""
        ).strip()
        if provided_confirmation != deletion_confirmation:
            raise ValueError(
                "삭제 후보 또는 검사 입력이 직전 점검과 달라졌습니다. 다시 검사한 뒤 삭제하세요."
            )
        log(f"삭제 예정 파일 {len(deletion_candidates)}개 삭제 중...")
        deletion_cleanup_warning = _delete_candidates_as_batch(
            base,
            validated_candidates,
        )
        log("파일 삭제 완료.")
        if deletion_cleanup_warning:
            log(deletion_cleanup_warning)

    log("폴더 검증 요약 데이터 구성 중...")
    statuses = [
        _download_integrity_status(
            folder,
            page_size,
            precomputed_statuses.get(str(folder)),
            precomputed_file_states.get(str(folder)),
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
        "deletion_confirmation": deletion_confirmation,
        "deletion_cleanup_warning": deletion_cleanup_warning,
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
