"""Disclosure HTML output inspection and cleanup helpers."""

from __future__ import annotations

from finiq.market_desk.web.features.disclosures import internal_html_download
from finiq.market_desk.web.features.disclosures.html_common import *


def _load_internal_html_integrity_source(
    body: dict[str, Any],
) -> tuple[Any, str, list[str], dict[str, str]]:
    if "source_directory" in body:
        raise ValueError(
            "source_directory is not supported; use source_compressed_json_path"
        )
    source_compressed_json_path_raw = str(
        body.get("source_compressed_json_path") or ""
    ).strip()
    if not source_compressed_json_path_raw:
        raise ValueError("source_compressed_json_path is required")
    source_path = Path(source_compressed_json_path_raw).expanduser().resolve()
    source_json = internal_html_download._load_compressed_external_html_file_payload(
        source_path
    )
    if body.get("parent_mode") not in (None, ""):
        filtered_json, _filtered_path = _load_workspace_filtered_payload(body)
        child_acpt_numbers = collect_acpt_numbers_from_json(filtered_json)
        records_by_acpt_no = {
            acpt_no: record
            for record, acpt_no in internal_html_download._validated_compressed_records(
                source_json
            )
        }
        missing = [
            acpt_no
            for acpt_no in child_acpt_numbers
            if acpt_no not in records_by_acpt_no
        ]
        if missing:
            raise ValueError(
                "parent compressed external records are missing derived targets: "
                + ", ".join(missing[:10])
            )
        source_json = {
            **source_json,
            "records": [records_by_acpt_no[acpt_no] for acpt_no in child_acpt_numbers],
        }
    if body.get("parent_mode") not in (None, ""):
        targets, source_json = (
            internal_html_download._collect_internal_targets_from_compressed_payload(
                source_json
            )
        )
    else:
        targets, source_json = (
            internal_html_download._collect_internal_cleanup_targets_from_compressed_payload(
                source_json
            )
        )

    targets = _apply_limit_to_targets(targets, body.get("limit"))
    acpt_numbers = [target["acpt_no"] for target in targets]
    target_years = {target["acpt_no"]: target["year"] for target in targets}
    return source_json, str(source_path), acpt_numbers, target_years


def _clean_disclosure_html_output_directory_payload(
    body: dict[str, Any],
    *,
    collect_integrity: bool,
) -> dict[str, Any]:
    """Delete files that would block HTML download resume from the output directory."""
    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        msg = "output_directory is required"
        raise ValueError(msg)
    source_compressed_json_path_raw = str(
        body.get("source_compressed_json_path") or ""
    ).strip()

    if "source_directory" in body or source_compressed_json_path_raw:
        _source_json, source_path, acpt_numbers, target_years = (
            _load_internal_html_integrity_source(body)
        )
        source_type = "content"
    else:
        source_json, source_path = _load_workspace_filtered_payload(body)
        acpt_numbers = collect_acpt_numbers_from_json(source_json)
        if not acpt_numbers:
            msg = "No acpt_no values found in JSON"
            raise ValueError(msg)
        acpt_numbers = _apply_limit_to_acpt_numbers(acpt_numbers, body.get("limit"))
        target_years = _target_years_from_json(source_json, acpt_numbers)
        source_type = "external"

    resolved_output_directory = Path(output_directory).expanduser().resolve()
    _ensure_safe_html_cleanup_directory(resolved_output_directory)
    dry_run = bool(body.get("dry_run", False))
    if body.get("parent_mode") not in (None, ""):
        # Derived filters inspect a subset of parent-owned HTML and never delete it.
        output_summary = _validate_html_output_directory_files(
            resolved_output_directory,
            acpt_numbers,
            target_years=target_years,
            allow_unexpected=True,
            collect_integrity=collect_integrity,
            problem_file_limit=body.get("problem_file_limit"),
        )
        output_summary["unexpected_file_count"] = 0
        output_summary["unexpected_files"] = []
        output_summary["unexpected_file_omitted_count"] = 0
        output_summary["deleted_files"] = []
        return {
            "format": "kind_disclosure_html_folder_cleanup_v1",
            "source_type": source_type,
            "source_path": source_path,
            "output_directory": str(resolved_output_directory),
            "dry_run": dry_run,
            "requested_count": len(acpt_numbers),
            "deleted_count": 0,
            "deletion_candidate_count": 0,
            "deletion_candidates": [],
            **output_summary,
        }
    if not dry_run and not _is_delete_confirmed(body):
        planned_summary = _delete_unexpected_html_output_directory_files(
            resolved_output_directory,
            acpt_numbers,
            target_years=target_years,
            dry_run=True,
            problem_file_limit=body.get("problem_file_limit"),
        )
        if planned_summary["deleted_files"]:
            msg = f'파일 삭제 전 "{HTML_DELETE_CONFIRMATION_TEXT}" 입력과 삭제 허가가 필요합니다.'
            raise ValueError(msg)

    summary = _delete_unexpected_html_output_directory_files(
        resolved_output_directory,
        acpt_numbers,
        target_years=target_years,
        dry_run=dry_run,
        collect_integrity=collect_integrity,
        problem_file_limit=body.get("problem_file_limit"),
    )
    deletion_candidate_count = int(summary.get("deleted_file_count") or 0)
    return {
        "format": "kind_disclosure_html_folder_cleanup_v1",
        "source_type": source_type,
        "source_path": source_path,
        "output_directory": str(resolved_output_directory),
        "dry_run": dry_run,
        "requested_count": len(acpt_numbers),
        "deleted_count": 0 if dry_run else deletion_candidate_count,
        "deletion_candidate_count": deletion_candidate_count,
        "deletion_candidates": summary["deleted_files"],
        **summary,
    }


def clean_disclosure_html_output_directory_payload(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Delete files that would block HTML download resume from the output directory."""
    return _clean_disclosure_html_output_directory_payload(
        body,
        collect_integrity=False,
    )


def check_disclosure_html_output_directory_payload(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Inspect existing HTML download files without deleting anything."""
    payload = dict(body)
    payload["dry_run"] = True
    summary = _clean_disclosure_html_output_directory_payload(
        payload,
        collect_integrity=True,
    )
    actual_integrity_by_acpt_no = summary.pop(
        "_target_integrity_by_acpt_no"
    )
    if summary.get("source_type") == "external":
        source_json, _source_json_path = _load_workspace_filtered_payload(body)
        acpt_numbers = collect_acpt_numbers_from_json(source_json)
        acpt_numbers = _apply_limit_to_acpt_numbers(acpt_numbers, body.get("limit"))
        integrity_summary = _inspect_html_integrity(
            Path(summary["output_directory"]),
            acpt_numbers,
            source_json=source_json,
            structurally_valid_acpt_numbers=summary[
                "existing_target_acpt_numbers"
            ],
            actual_integrity_by_acpt_no=actual_integrity_by_acpt_no,
        )
        integrity_summary.pop("_verified_integrity_by_acpt_no", None)
        summary.update(integrity_summary)
    elif summary.get("source_type") == "content":
        source_json, _source_path, acpt_numbers, _target_years = (
            _load_internal_html_integrity_source(body)
        )
        integrity_summary = _inspect_html_integrity(
            Path(summary["output_directory"]),
            acpt_numbers,
            source_json=source_json,
            structurally_valid_acpt_numbers=summary[
                "existing_target_acpt_numbers"
            ],
            actual_integrity_by_acpt_no=actual_integrity_by_acpt_no,
        )
        integrity_summary.pop("_verified_integrity_by_acpt_no", None)
        summary.update(integrity_summary)
    if summary.get("source_type") in {"external", "content"}:
        summary["download_required_target_html_count"] = (
            int(summary.get("missing_target_html_count") or 0)
            + int(summary.get("hash_mismatch_target_html_count") or 0)
        )
    existing_count = int(summary.get("existing_target_html_count") or 0)
    total_file_count = int(summary.get("total_file_count") or 0)
    return {
        **summary,
        "format": "kind_disclosure_html_existing_check_v1",
        "has_existing": existing_count > 0 or total_file_count > 0,
    }


def create_external_html_integrity_baseline_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Trust the current external HTML files and record their integrity baseline."""
    if body.get("trust_existing_files") is not True:
        raise ValueError("현재 외부 HTML 신뢰 확인이 필요합니다.")

    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        raise ValueError("output_directory is required")
    resolved_output_directory = Path(output_directory).expanduser().resolve()
    _ensure_safe_html_cleanup_directory(resolved_output_directory)

    source_json, _source_json_path = _load_workspace_filtered_payload(body)
    acpt_numbers = collect_acpt_numbers_from_json(source_json)
    if not acpt_numbers:
        raise ValueError("No acpt_no values found in JSON")
    acpt_numbers = _apply_limit_to_acpt_numbers(acpt_numbers, body.get("limit"))
    target_years = _target_years_from_json(source_json, acpt_numbers)
    if body.get("parent_mode") not in (None, ""):
        saved_paths, _verification = _strictly_reuse_parent_html(
            output_directory=resolved_output_directory,
            acpt_numbers=acpt_numbers,
            source_json=source_json,
        )
        return {
            "format": "finiq_disclosure_external_html_integrity_baseline_v1",
            "cancelled": False,
            "reused_parent_html": True,
            "output_directory": str(resolved_output_directory),
            "requested_count": len(acpt_numbers),
            "hashed_count": len(saved_paths),
            "manifest_path": str(
                resolved_output_directory / HTML_MANIFEST_FILENAME
            ),
        }
    try:
        output_summary = _validate_html_output_directory_files(
            resolved_output_directory,
            acpt_numbers,
            target_years=target_years,
            collect_integrity=True,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
    except InterruptedError:
        return {
            "format": "finiq_disclosure_external_html_integrity_baseline_v1",
            "cancelled": True,
            "output_directory": str(resolved_output_directory),
            "requested_count": len(acpt_numbers),
            "hashed_count": 0,
        }
    baseline_acpt_numbers = output_summary["existing_target_acpt_numbers"]
    if not baseline_acpt_numbers:
        raise ValueError("기준 해시를 생성할 정상 외부 HTML이 없습니다.")

    source_integrity = output_summary.pop("_target_integrity_by_acpt_no")
    if progress_callback is not None:
        progress_callback(
            f"현재 외부 HTML {len(baseline_acpt_numbers)}건의 기준 해시를 생성합니다."
        )

    manifest_path = _write_html_manifest(
        output_directory=resolved_output_directory,
        acpt_numbers=baseline_acpt_numbers,
        source_json=source_json,
        source_integrity=source_integrity,
    )
    if progress_callback is not None:
        progress_callback(f"외부 HTML 기준 해시 저장 완료: {manifest_path}")
    return {
        "format": "finiq_disclosure_external_html_integrity_baseline_v1",
        "cancelled": False,
        "output_directory": str(resolved_output_directory),
        "requested_count": len(acpt_numbers),
        "hashed_count": len(source_integrity),
        "manifest_path": str(manifest_path),
    }


def create_internal_html_integrity_baseline_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Trust the current internal HTML files and record their integrity baseline."""
    if body.get("trust_existing_files") is not True:
        raise ValueError("현재 내부 HTML 신뢰 확인이 필요합니다.")

    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        raise ValueError("output_directory is required")
    resolved_output_directory = Path(output_directory).expanduser().resolve()
    _ensure_safe_html_cleanup_directory(resolved_output_directory)

    source_json, _source_path, acpt_numbers, target_years = (
        _load_internal_html_integrity_source(body)
    )
    if body.get("parent_mode") not in (None, ""):
        saved_paths, _verification = _strictly_reuse_parent_html(
            output_directory=resolved_output_directory,
            acpt_numbers=acpt_numbers,
            source_json=source_json,
        )
        return {
            "format": "finiq_disclosure_internal_html_integrity_baseline_v1",
            "cancelled": False,
            "reused_parent_html": True,
            "output_directory": str(resolved_output_directory),
            "requested_count": len(acpt_numbers),
            "hashed_count": len(saved_paths),
            "manifest_path": str(
                resolved_output_directory / HTML_MANIFEST_FILENAME
            ),
        }
    try:
        output_summary = _validate_html_output_directory_files(
            resolved_output_directory,
            acpt_numbers,
            target_years=target_years,
            collect_integrity=True,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
    except InterruptedError:
        return {
            "format": "finiq_disclosure_internal_html_integrity_baseline_v1",
            "cancelled": True,
            "output_directory": str(resolved_output_directory),
            "requested_count": len(acpt_numbers),
            "hashed_count": 0,
        }
    baseline_acpt_numbers = output_summary["existing_target_acpt_numbers"]
    if not baseline_acpt_numbers:
        raise ValueError("기준 해시를 생성할 정상 내부 HTML이 없습니다.")

    source_integrity = output_summary.pop("_target_integrity_by_acpt_no")
    if progress_callback is not None:
        progress_callback(
            f"현재 내부 HTML {len(baseline_acpt_numbers)}건의 기준 해시를 생성합니다."
        )

    manifest_path = _write_html_manifest(
        output_directory=resolved_output_directory,
        acpt_numbers=baseline_acpt_numbers,
        source_json=source_json,
        source_integrity=source_integrity,
    )
    if progress_callback is not None:
        progress_callback(f"내부 HTML 기준 해시 저장 완료: {manifest_path}")
    return {
        "format": "finiq_disclosure_internal_html_integrity_baseline_v1",
        "cancelled": False,
        "output_directory": str(resolved_output_directory),
        "requested_count": len(acpt_numbers),
        "hashed_count": len(source_integrity),
        "manifest_path": str(manifest_path),
    }


def write_disclosure_html_manifest_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Write the HTML manifest for an already materialized output directory."""
    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        msg = "output_directory is required"
        raise ValueError(msg)

    resolved_output_directory = Path(output_directory).expanduser().resolve()
    if "source_directory" in body:
        msg = "source_directory is not supported; use source_compressed_json_path"
        raise ValueError(msg)
    source_compressed_json_path_raw = str(
        body.get("source_compressed_json_path") or ""
    ).strip()
    resolved_source_path = ""

    if source_compressed_json_path_raw:
        source_compressed_json_path = (
            Path(source_compressed_json_path_raw).expanduser().resolve()
        )
        source_json = internal_html_download._load_compressed_external_html_file_payload(
            source_compressed_json_path
        )
        targets, source_json = (
            internal_html_download._collect_internal_targets_from_compressed_payload(
                source_json
            )
        )
        targets = _apply_limit_to_targets(targets, body.get("limit"))
        acpt_numbers = [target["acpt_no"] for target in targets]
        resolved_source_path = str(source_compressed_json_path)
    else:
        source_json, resolved_source_path = _load_workspace_filtered_payload(body)
        acpt_numbers = collect_acpt_numbers_from_json(source_json)
        if not acpt_numbers:
            msg = "No acpt_no values found in JSON"
            raise ValueError(msg)
        acpt_numbers = _apply_limit_to_acpt_numbers(acpt_numbers, body.get("limit"))

    manifest_path = _write_html_manifest(
        output_directory=resolved_output_directory,
        acpt_numbers=acpt_numbers,
        source_json=source_json,
    )
    return {
        "format": "finiq_disclosure_html_manifest_write_v1",
        "output_directory": str(resolved_output_directory),
        "source_path": resolved_source_path,
        "requested_count": len(acpt_numbers),
        "manifest_path": str(manifest_path),
    }
