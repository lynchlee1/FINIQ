"""Disclosure HTML output inspection and cleanup helpers."""

from __future__ import annotations

from finiq.market_desk.web.features.disclosures import internal_html_download
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
)
from finiq.market_desk.web.features.disclosures.filter_presets import (
    manage_filter_presets_payload,
)
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


def _load_html_integrity_source(
    body: dict[str, Any],
) -> tuple[Any, str, list[str], dict[str, str], str]:
    source_compressed_json_path_raw = str(
        body.get("source_compressed_json_path") or ""
    ).strip()
    if "source_directory" in body or source_compressed_json_path_raw:
        source_json, source_path, acpt_numbers, target_years = (
            _load_internal_html_integrity_source(body)
        )
        return source_json, source_path, acpt_numbers, target_years, "content"

    source_json, source_path = _load_workspace_filtered_payload(body)
    acpt_numbers = collect_acpt_numbers_from_json(source_json)
    if not acpt_numbers:
        raise ValueError("No acpt_no values found in JSON")
    acpt_numbers = _apply_limit_to_acpt_numbers(acpt_numbers, body.get("limit"))
    target_years = _target_years_from_json(source_json, acpt_numbers)
    return source_json, source_path, acpt_numbers, target_years, "external"


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
    source_json, source_path, acpt_numbers, target_years, source_type = (
        _load_html_integrity_source(body)
    )

    def with_source_context(result: dict[str, Any]) -> dict[str, Any]:
        if collect_integrity:
            result["_source_json"] = source_json
            result["_source_acpt_numbers"] = acpt_numbers
        return result

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
        return with_source_context(
            {
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
        )
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
    return with_source_context(
        {
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
    )


def clean_disclosure_html_output_directory_payload(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Delete files that would block HTML download resume from the output directory."""
    return _clean_disclosure_html_output_directory_payload(
        body,
        collect_integrity=False,
    )


def _check_disclosure_html_output_directory_payload(
    body: dict[str, Any],
    *,
    return_scan_context: bool = False,
) -> dict[str, Any]:
    """Inspect existing HTML download files without deleting anything."""
    payload = dict(body)
    payload["dry_run"] = True
    summary = _clean_disclosure_html_output_directory_payload(
        payload,
        collect_integrity=True,
    )
    source_json = summary.pop("_source_json")
    acpt_numbers = summary.pop("_source_acpt_numbers")
    actual_integrity_by_acpt_no = summary.pop(
        "_target_integrity_by_acpt_no"
    )
    output_directory = Path(summary["output_directory"])
    loaded_manifest_integrity = _load_html_manifest_integrity(output_directory)
    selected_doc_numbers = _selected_main_doc_numbers(source_json)
    recorded_source_unavailable = _load_html_manifest_source_unavailable(
        output_directory
    )
    source_unavailable_acpt_numbers = [
        acpt_no
        for acpt_no in summary["missing_target_acpt_numbers"]
        if selected_doc_numbers.get(acpt_no)
        and recorded_source_unavailable.get(acpt_no, {}).get("doc_no")
        == selected_doc_numbers.get(acpt_no)
    ]
    if source_unavailable_acpt_numbers:
        unavailable_set = set(source_unavailable_acpt_numbers)
        summary["missing_target_acpt_numbers"] = [
            acpt_no
            for acpt_no in summary["missing_target_acpt_numbers"]
            if acpt_no not in unavailable_set
        ]
        summary["missing_target_html_count"] = len(
            summary["missing_target_acpt_numbers"]
        )
    summary["source_unavailable_target_html_count"] = len(
        source_unavailable_acpt_numbers
    )
    summary["source_unavailable_target_acpt_numbers"] = (
        source_unavailable_acpt_numbers
    )
    integrity_summary = _inspect_html_integrity(
        output_directory,
        acpt_numbers,
        source_json=source_json,
        structurally_valid_acpt_numbers=summary["existing_target_acpt_numbers"],
        actual_integrity_by_acpt_no=actual_integrity_by_acpt_no,
        loaded_manifest_integrity=loaded_manifest_integrity,
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
    result = {
        **summary,
        "format": "kind_disclosure_html_existing_check_v1",
        "has_existing": existing_count > 0 or total_file_count > 0,
    }
    if return_scan_context:
        result["_scan_context"] = {
            "owner_acpt_numbers": acpt_numbers,
            "structurally_valid_acpt_numbers": summary[
                "existing_target_acpt_numbers"
            ],
            "invalid_target_acpt_numbers": summary["invalid_target_acpt_numbers"],
            "source_unavailable_target_acpt_numbers": source_unavailable_acpt_numbers,
            "actual_integrity_by_acpt_no": actual_integrity_by_acpt_no,
            "loaded_manifest_integrity": loaded_manifest_integrity,
        }
    return result


def check_disclosure_html_output_directory_payload(
    body: dict[str, Any],
) -> dict[str, Any]:
    return _check_disclosure_html_output_directory_payload(body)


def _check_derived_html_from_owner_scan(
    body: dict[str, Any],
    owner_result: dict[str, Any],
    owner_scan: dict[str, Any],
) -> dict[str, Any]:
    source_json, source_path, acpt_numbers, _target_years, source_type = (
        _load_html_integrity_source(body)
    )
    owner_acpt_numbers = set(owner_scan["owner_acpt_numbers"])
    missing_from_owner = [
        acpt_no for acpt_no in acpt_numbers if acpt_no not in owner_acpt_numbers
    ]
    if missing_from_owner:
        raise ValueError(
            "derived filter targets are missing from the parent filter: "
            + ", ".join(missing_from_owner[:10])
        )

    structurally_valid = set(owner_scan["structurally_valid_acpt_numbers"])
    invalid = set(owner_scan["invalid_target_acpt_numbers"])
    owner_source_unavailable = set(
        owner_scan["source_unavailable_target_acpt_numbers"]
    )
    selected_doc_numbers = _selected_main_doc_numbers(source_json)
    recorded_source_unavailable = _load_html_manifest_source_unavailable(
        Path(owner_result["output_directory"])
    )
    source_unavailable_acpt_numbers = [
        acpt_no
        for acpt_no in acpt_numbers
        if acpt_no in owner_source_unavailable
        and selected_doc_numbers.get(acpt_no)
        and recorded_source_unavailable.get(acpt_no, {}).get("doc_no")
        == selected_doc_numbers.get(acpt_no)
    ]
    source_unavailable = set(source_unavailable_acpt_numbers)
    existing_target_acpt_numbers = [
        acpt_no for acpt_no in acpt_numbers if acpt_no in structurally_valid
    ]
    invalid_target_acpt_numbers = [
        acpt_no for acpt_no in acpt_numbers if acpt_no in invalid
    ]
    missing_target_acpt_numbers = [
        acpt_no
        for acpt_no in acpt_numbers
        if acpt_no not in structurally_valid and acpt_no not in source_unavailable
    ]
    actual_integrity_by_acpt_no = {
        acpt_no: owner_scan["actual_integrity_by_acpt_no"][acpt_no]
        for acpt_no in existing_target_acpt_numbers
    }
    output_directory = Path(owner_result["output_directory"])
    integrity_summary = _inspect_html_integrity(
        output_directory,
        acpt_numbers,
        source_json=source_json,
        structurally_valid_acpt_numbers=existing_target_acpt_numbers,
        actual_integrity_by_acpt_no=actual_integrity_by_acpt_no,
        loaded_manifest_integrity=owner_scan["loaded_manifest_integrity"],
    )
    integrity_summary.pop("_verified_integrity_by_acpt_no", None)
    download_required_count = (
        len(missing_target_acpt_numbers)
        + int(integrity_summary.get("hash_mismatch_target_html_count") or 0)
    )
    return {
        "format": "kind_disclosure_html_existing_check_v1",
        "source_type": source_type,
        "source_path": source_path,
        "output_directory": str(output_directory),
        "dry_run": True,
        "requested_count": len(acpt_numbers),
        "deleted_count": 0,
        "deletion_candidate_count": 0,
        "deletion_candidates": [],
        "existing_target_html_count": len(existing_target_acpt_numbers),
        "missing_target_html_count": len(missing_target_acpt_numbers),
        "existing_target_acpt_numbers": existing_target_acpt_numbers,
        "missing_target_acpt_numbers": missing_target_acpt_numbers,
        "source_unavailable_target_html_count": len(
            source_unavailable_acpt_numbers
        ),
        "source_unavailable_target_acpt_numbers": source_unavailable_acpt_numbers,
        "invalid_target_html_count": len(invalid_target_acpt_numbers),
        "invalid_target_acpt_numbers": invalid_target_acpt_numbers,
        "auxiliary_file_count": owner_result["auxiliary_file_count"],
        "total_file_count": owner_result["total_file_count"],
        "unexpected_file_count": 0,
        "unexpected_files": [],
        "unexpected_file_omitted_count": 0,
        "deleted_files": [],
        "deleted_file_count": 0,
        "deleted_file_omitted_count": 0,
        **integrity_summary,
        "download_required_target_html_count": download_required_count,
        "has_existing": bool(existing_target_acpt_numbers)
        or int(owner_result["total_file_count"]) > 0,
    }


def _inspect_all_disclosure_html_payload(
    body: dict[str, Any],
    *,
    workflow_kind: str,
    result_format: str,
) -> dict[str, Any]:
    data_root = str(body.get("data_root") or "").strip()
    if not data_root:
        raise ValueError("data_root is required")

    preset_response = manage_filter_presets_payload(
        {"data_root": data_root, "action": "list"}
    )
    presets = list(preset_response["presets"])
    results_by_id: dict[str, dict[str, Any]] = {}
    owner_scans: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}

    def inspect_preset(preset: dict[str, Any]) -> None:
        mode = preset["mode"]
        parent_mode = preset.get("parent_mode")
        payload = apply_workspace_defaults(
            workflow_kind,
            {
                "data_root": data_root,
                "mode": mode,
                **({"parent_mode": parent_mode} if parent_mode else {}),
                "problem_file_limit": body.get("problem_file_limit"),
            },
            create_workspace=False,
        )
        try:
            if parent_mode:
                owner = owner_scans.get(parent_mode)
                if owner is None:
                    raise ValueError(
                        f"parent HTML inspection is unavailable: {parent_mode}"
                    )
                inspected = _check_derived_html_from_owner_scan(
                    payload,
                    owner[0],
                    owner[1],
                )
            else:
                inspected = _check_disclosure_html_output_directory_payload(
                    payload,
                    return_scan_context=True,
                )
                owner_scan = inspected.pop("_scan_context")
                owner_scans[mode] = (inspected, owner_scan)
            problem_count = (
                int(inspected.get("download_required_target_html_count") or 0)
                + int(inspected.get("invalid_target_html_count") or 0)
                + int(inspected.get("hash_unverified_target_html_count") or 0)
                + int(inspected.get("deletion_candidate_count") or 0)
            )
            passed = problem_count == 0
        except Exception as exc:
            inspected = {
                "requested_count": 0,
                "existing_target_html_count": 0,
                "download_required_target_html_count": 0,
                "missing_target_html_count": 0,
                "invalid_target_html_count": 0,
                "hash_mismatch_target_html_count": 0,
                "hash_unverified_target_html_count": 0,
                "source_unavailable_target_html_count": 0,
                "deletion_candidate_count": 0,
                "error": str(exc),
            }
            passed = False
        results_by_id[preset["id"]] = {
            "id": preset["id"],
            "mode": mode,
            **({"parent_mode": parent_mode} if parent_mode else {}),
            **inspected,
            "passed": passed,
        }

    for preset in presets:
        if not preset.get("parent_mode"):
            inspect_preset(preset)
            for child in presets:
                if child.get("parent_mode") == preset["mode"]:
                    inspect_preset(child)
            owner_scans.pop(preset["mode"], None)
    for preset in presets:
        if preset["id"] not in results_by_id:
            inspect_preset(preset)

    results = [results_by_id[preset["id"]] for preset in presets]

    failed_modes = [result["id"] for result in results if not result["passed"]]
    count_fields = (
        "requested_count",
        "existing_target_html_count",
        "download_required_target_html_count",
        "missing_target_html_count",
        "invalid_target_html_count",
        "hash_mismatch_target_html_count",
        "hash_unverified_target_html_count",
        "source_unavailable_target_html_count",
        "deletion_candidate_count",
    )
    totals = {
        field: sum(int(result.get(field) or 0) for result in results)
        for field in count_fields
    }
    owner_results = [result for result in results if not result.get("parent_mode")]
    owner_totals = {
        f"owner_{field}": sum(int(result.get(field) or 0) for result in owner_results)
        for field in count_fields
    }
    return {
        "format": result_format,
        "passed": not failed_modes,
        "mode_count": len(results),
        "passed_mode_count": len(results) - len(failed_modes),
        "failed_mode_count": len(failed_modes),
        "failed_modes": failed_modes,
        **totals,
        **owner_totals,
        "results": results,
    }


def inspect_all_disclosure_external_html_payload(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Inspect saved external HTML for every workspace filter mode."""
    return _inspect_all_disclosure_html_payload(
        body,
        workflow_kind="external_html_download",
        result_format="finiq_disclosure_external_html_all_inspection_v1",
    )


def inspect_all_disclosure_internal_html_payload(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Inspect saved internal HTML for every workspace filter mode."""
    return _inspect_all_disclosure_html_payload(
        body,
        workflow_kind="internal_html_download",
        result_format="finiq_disclosure_internal_html_all_inspection_v1",
    )


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
