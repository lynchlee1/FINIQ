"""Disclosure HTML output inspection and cleanup helpers."""

from __future__ import annotations

from finiq.market_desk.web.features.disclosures import html_content_download
from finiq.market_desk.web.features.disclosures.html_common import *

def clean_disclosure_html_output_directory_payload(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Delete files that would block HTML download resume from the output directory."""
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
    if source_compressed_json_path_raw:
        source_compressed_json_path = (
            Path(source_compressed_json_path_raw).expanduser().resolve()
        )
        compressed_payload = html_content_download._load_compressed_external_html_file_payload(
            source_compressed_json_path
        )
        targets, _manifest_payload = (
            html_content_download._collect_content_cleanup_targets_from_compressed_payload(compressed_payload)
        )
        targets = _apply_limit_to_targets(targets, body.get("limit"))
        acpt_numbers = [target["acpt_no"] for target in targets]
        target_years = {
            target["acpt_no"]: target.get("year")
            or _year_from_disclosure(target["acpt_no"])
            for target in targets
        }
        source_type = "content"
        source_path = str(source_compressed_json_path)
    elif source_directory_raw:
        source_directory = Path(source_directory_raw).expanduser().resolve()
        targets, _manifest_payload = (
            html_content_download._collect_content_cleanup_targets_from_external_directory(
                source_directory,
            )
        )
        targets = _apply_limit_to_targets(targets, body.get("limit"))
        acpt_numbers = [target["acpt_no"] for target in targets]
        target_years = {
            target["acpt_no"]: target.get("year")
            or _year_from_disclosure(target["acpt_no"])
            for target in targets
        }
        source_type = "content"
        source_path = str(source_directory)
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
    if not dry_run and not _is_delete_confirmed(body):
        planned_summary = _delete_unexpected_html_output_directory_files(
            resolved_output_directory,
            acpt_numbers,
            target_years=target_years,
            dry_run=True,
        )
        if planned_summary["deleted_files"]:
            msg = f'파일 삭제 전 "{HTML_DELETE_CONFIRMATION_TEXT}" 입력과 삭제 허가가 필요합니다.'
            raise ValueError(msg)

    summary = _delete_unexpected_html_output_directory_files(
        resolved_output_directory,
        acpt_numbers,
        target_years=target_years,
        dry_run=dry_run,
    )
    return {
        "format": "kind_disclosure_html_folder_cleanup_v1",
        "source_type": source_type,
        "source_path": source_path,
        "output_directory": str(resolved_output_directory),
        "dry_run": dry_run,
        "requested_count": len(acpt_numbers),
        "deleted_count": 0 if dry_run else len(summary["deleted_files"]),
        "deletion_candidate_count": len(summary["deleted_files"]),
        "deletion_candidates": summary["deleted_files"],
        **summary,
    }


def check_disclosure_html_output_directory_payload(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Inspect existing HTML download files without deleting anything."""
    payload = dict(body)
    payload["dry_run"] = True
    summary = clean_disclosure_html_output_directory_payload(payload)
    existing_count = int(summary.get("existing_target_html_count") or 0)
    total_file_count = int(summary.get("total_file_count") or 0)
    return {
        **summary,
        "format": "kind_disclosure_html_existing_check_v1",
        "has_existing": existing_count > 0 or total_file_count > 0,
    }


def write_disclosure_html_manifest_payload(body: dict[str, Any]) -> dict[str, Any]:
    """Write the HTML manifest for an already materialized output directory."""
    output_directory = str(body.get("output_directory") or "").strip()
    if not output_directory:
        msg = "output_directory is required"
        raise ValueError(msg)

    resolved_output_directory = Path(output_directory).expanduser().resolve()
    source_directory_raw = str(body.get("source_directory") or "").strip()
    source_compressed_json_path_raw = str(
        body.get("source_compressed_json_path") or ""
    ).strip()
    resolved_source_path = ""

    if source_directory_raw and source_compressed_json_path_raw:
        msg = "source_directory and source_compressed_json_path cannot be used together"
        raise ValueError(msg)
    if source_compressed_json_path_raw:
        source_compressed_json_path = (
            Path(source_compressed_json_path_raw).expanduser().resolve()
        )
        source_json = html_content_download._load_compressed_external_html_file_payload(
            source_compressed_json_path
        )
        targets, manifest_payload = html_content_download._collect_content_targets_from_compressed_payload(
            source_json
        )
        targets = _apply_limit_to_targets(targets, body.get("limit"))
        acpt_numbers = [target["acpt_no"] for target in targets]
        source_json = manifest_payload
        resolved_source_path = str(source_compressed_json_path)
    elif source_directory_raw:
        source_directory = Path(source_directory_raw).expanduser().resolve()
        targets, manifest_payload = html_content_download._collect_content_targets_from_external_directory(
            source_directory,
        )
        targets = _apply_limit_to_targets(targets, body.get("limit"))
        acpt_numbers = [target["acpt_no"] for target in targets]
        source_json = manifest_payload or {
            "disclosures": [{"acpt_no": acpt_no} for acpt_no in acpt_numbers]
        }
        resolved_source_path = str(source_directory)
    else:
        source_json, resolved_source_path = _load_workspace_filtered_payload(body)
        acpt_numbers = collect_acpt_numbers_from_json(source_json)
        if not acpt_numbers:
            msg = "No acpt_no values found in JSON"
            raise ValueError(msg)
        acpt_numbers = _apply_limit_to_acpt_numbers(acpt_numbers, body.get("limit"))

    manifest_path = _write_html_manifest(
        output_directory=resolved_output_directory,
        source_json_path=resolved_source_path,
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
