"""Compressed external disclosure HTML payload helpers."""

from __future__ import annotations

from collections import deque
import os
import shutil
import tempfile

from finiq.concurrency import bounded_as_completed
from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
    atomic_write_json,
)
from finiq.market_desk.web.features.disclosures.filter_presets import (
    manage_filter_presets_payload,
)
from finiq.market_desk.web.features.disclosures.html_common import *
from finiq.market_desk.web.features.disclosures.html_common import (
    _parse_progress_interval,
)

_REQUEST_METADATA = object()


def _validate_external_html_manifest_integrity(
    *,
    input_directory: Path,
    records: list[dict[str, Any]],
) -> None:
    (
        manifest_format,
        _source_fingerprint,
        expected_integrity,
        _selected_doc_numbers,
    ) = _load_html_manifest_integrity(input_directory)
    if not manifest_format:
        raise ValueError(
            "external HTML manifest integrity baseline is missing: "
            f"{input_directory / HTML_MANIFEST_FILENAME}"
        )

    unverified: list[str] = []
    mismatched: list[str] = []
    for record in records:
        acpt_no = str(record.get("acpt_no") or "").strip()
        expected = expected_integrity.get(acpt_no)
        if expected is None:
            unverified.append(acpt_no)
            continue
        if (
            record.get("source_sha256") != expected["source_sha256"]
            or record.get("source_size_bytes") != expected["source_size_bytes"]
        ):
            mismatched.append(acpt_no)
    if unverified or mismatched:
        details: list[str] = []
        if unverified:
            details.append("unverified=" + ", ".join(unverified[:10]))
        if mismatched:
            details.append("mismatched=" + ", ".join(mismatched[:10]))
        raise ValueError(
            "external HTML manifest integrity check failed: " + "; ".join(details)
        )


def _inspect_external_html_compression_without_source(
    compressed_path: Path,
    *,
    compressed_exists: bool,
) -> dict[str, Any]:
    if compressed_exists:
        verification = _verify_compressed_external_html_files(
            written_files=[str(compressed_path)],
            expected_acpt_numbers=[],
        )
        return {
            "format": "finiq_disclosure_external_html_compress_inspection_v1",
            "compressed_path": str(compressed_path),
            **verification,
            "passed": False,
            "skipped": False,
            "orphaned_output": True,
            "content_matches_source": False,
            "error": "원본 HTML이 없지만 이전 압축 JSON이 남아 있습니다.",
        }
    return {
        "format": "finiq_disclosure_external_html_compress_inspection_v1",
        "compressed_path": str(compressed_path),
        "passed": True,
        "skipped": True,
        "expected_records": 0,
        "verified_records": 0,
        "missing_records": 0,
        "unexpected_records": 0,
        "duplicate_records": 0,
        "missing_files": [],
        "invalid_files": [],
        "content_matches_source": True,
        "orphaned_output": False,
        "error": "",
    }


def _external_html_compression_owner_state(
    *,
    input_directory: Path,
    compressed_path: Path,
) -> dict[str, Any]:
    html_files = (
        _collect_yearly_html_files(input_directory)
        if input_directory.exists()
        else []
    )
    expected_acpt_numbers = [html_path.stem for _year, html_path in html_files]
    source_integrity_by_acpt_no: dict[str, dict[str, Any]] = {}
    invalid_source_acpt_numbers: list[str] = []
    manifest_unverified_acpt_numbers: list[str] = []
    manifest_mismatch_acpt_numbers: list[str] = []
    manifest_error = ""
    if html_files:
        target_years = {
            html_path.stem: year for year, html_path in html_files
        }
        source_summary = _validate_html_output_directory_files(
            input_directory,
            expected_acpt_numbers,
            target_years=target_years,
            allow_unexpected=True,
            collect_integrity=True,
        )
        source_integrity_by_acpt_no = source_summary.pop(
            "_target_integrity_by_acpt_no"
        )
        invalid_source_acpt_numbers = list(
            source_summary["invalid_target_acpt_numbers"]
        )
        try:
            (
                manifest_format,
                _source_fingerprint,
                expected_integrity,
                _selected_doc_numbers,
            ) = _load_html_manifest_integrity(input_directory)
            if not manifest_format:
                manifest_error = (
                    "external HTML manifest integrity baseline is missing: "
                    f"{input_directory / HTML_MANIFEST_FILENAME}"
                )
            else:
                manifest_unverified_acpt_numbers = [
                    acpt_no
                    for acpt_no in expected_acpt_numbers
                    if acpt_no not in expected_integrity
                ]
                manifest_mismatch_acpt_numbers = [
                    acpt_no
                    for acpt_no, actual in source_integrity_by_acpt_no.items()
                    if acpt_no in expected_integrity
                    and actual != expected_integrity[acpt_no]
                ]
        except Exception as exc:
            manifest_error = str(exc)

    compressed_exists = compressed_path.is_file()
    verification = _verify_compressed_external_html_files(
        written_files=[str(compressed_path)],
        expected_acpt_numbers=expected_acpt_numbers,
    )
    compressed_payload: Any = None
    compressed_records: list[Any] = []
    compressed_format_valid = False
    if compressed_exists:
        try:
            compressed_payload = json.loads(
                compressed_path.read_text(encoding="utf-8")
            )
            compressed_records = (
                compressed_payload.get("records")
                if isinstance(compressed_payload, dict)
                and isinstance(compressed_payload.get("records"), list)
                else []
            )
            compressed_format_valid = (
                isinstance(compressed_payload, dict)
                and compressed_payload.get("format")
                == "finiq_disclosure_external_html_docs_v1"
                and isinstance(compressed_payload.get("records"), list)
            )
        except Exception:
            pass
    return {
        "expected_acpt_numbers": expected_acpt_numbers,
        "source_integrity_by_acpt_no": source_integrity_by_acpt_no,
        "invalid_source_acpt_numbers": invalid_source_acpt_numbers,
        "manifest_unverified_acpt_numbers": manifest_unverified_acpt_numbers,
        "manifest_mismatch_acpt_numbers": manifest_mismatch_acpt_numbers,
        "manifest_error": manifest_error,
        "compressed_exists": compressed_exists,
        "verification": verification,
        "compressed_records": compressed_records,
        "compressed_format_valid": compressed_format_valid,
    }


def _workspace_filter_presets(data_root: object) -> list[dict[str, Any]]:
    response = manage_filter_presets_payload(
        {"data_root": data_root, "action": "list"}
    )
    return list(response["presets"])


def inspect_all_disclosure_external_html_compress_payload(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Verify compressed external HTML for every workspace filter mode."""
    data_root = str(body.get("data_root") or "").strip()
    if not data_root:
        raise ValueError("data_root is required")

    results: list[dict[str, Any]] = []
    owner_states: dict[tuple[str, str], dict[str, Any]] = {}
    for preset in _workspace_filter_presets(data_root):
        mode = preset["mode"]
        parent_mode = preset.get("parent_mode")
        payload = apply_workspace_defaults(
            "external_html_compress",
            {
                "data_root": data_root,
                "mode": mode,
                **({"parent_mode": parent_mode} if parent_mode else {}),
                "parallel_workers": body.get("parallel_workers"),
                "progress_interval": body.get("progress_interval"),
            },
            create_workspace=False,
        )
        try:
            owner_key = (
                str(payload["input_directory"]),
                str(payload["output_directory"]),
            )
            owner_state = owner_states.get(owner_key)
            if owner_state is None:
                input_directory = Path(owner_key[0]).expanduser().resolve()
                compressed_path = (
                    Path(owner_key[1]).expanduser().resolve()
                    / COMPRESSED_EXTERNAL_HTML_FILENAME
                )
                owner_state = _external_html_compression_owner_state(
                    input_directory=input_directory,
                    compressed_path=compressed_path,
                )
                owner_states[owner_key] = owner_state
            inspected = inspect_disclosure_external_html_compress_payload(
                payload,
                _owner_state=owner_state,
            )
        except Exception as exc:
            inspected = {
                "passed": False,
                "expected_records": 0,
                "verified_records": 0,
                "missing_records": 0,
                "unexpected_records": 0,
                "duplicate_records": 0,
                "missing_files": [],
                "invalid_files": [],
                "content_matches_source": False,
                "error": str(exc),
            }
        results.append(
            {
                "id": preset["id"],
                "mode": mode,
                **({"parent_mode": parent_mode} if parent_mode else {}),
                **inspected,
                "repairable": (
                    not parent_mode
                    and not inspected["passed"]
                    and not inspected.get("orphaned_output", False)
                ),
            }
        )

    failed_modes = [result["id"] for result in results if not result["passed"]]
    skipped_modes = [result["id"] for result in results if result.get("skipped")]
    repairable_failed_modes = [
        result["id"] for result in results if result["repairable"]
    ]
    return {
        "format": "finiq_disclosure_external_html_compress_all_inspection_v1",
        "passed": not failed_modes,
        "mode_count": len(results),
        "passed_mode_count": len(results) - len(failed_modes),
        "failed_mode_count": len(failed_modes),
        "failed_modes": failed_modes,
        "skipped_mode_count": len(skipped_modes),
        "skipped_modes": skipped_modes,
        "repairable_failed_mode_count": len(repairable_failed_modes),
        "repairable_failed_modes": repairable_failed_modes,
        "expected_records": sum(result["expected_records"] for result in results),
        "verified_records": sum(result["verified_records"] for result in results),
        "results": results,
    }


def rebuild_invalid_disclosure_external_html_compress_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Rebuild only owner files implicated by the current all-mode inspection."""
    data_root = str(body.get("data_root") or "").strip()
    if not data_root:
        raise ValueError("data_root is required")

    inspection = inspect_all_disclosure_external_html_compress_payload(body)
    owner_modes = sorted(
        {
            result["mode"]
            for result in inspection["results"]
            if result["repairable"]
        }
    )
    results: list[dict[str, Any]] = []
    cancelled = False
    for index, mode in enumerate(owner_modes, start=1):
        if cancel_check is not None and cancel_check():
            cancelled = True
            break
        if progress_callback is not None:
            progress_callback(
                f"재생성 {index}/{len(owner_modes)}: {mode}"
            )
        payload = apply_workspace_defaults(
            "external_html_compress",
            {
                "data_root": data_root,
                "mode": mode,
                "parallel_workers": body.get("parallel_workers"),
                "progress_interval": body.get("progress_interval"),
            },
        )
        try:
            result = compress_disclosure_external_html_payload(
                payload,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
            results.append({"mode": mode, "passed": True, **result})
        except Exception as exc:
            results.append(
                {"mode": mode, "passed": False, "error": str(exc)}
            )
        if cancel_check is not None and cancel_check():
            cancelled = True
            break

    failed_modes = [result["mode"] for result in results if not result["passed"]]
    verification = (
        inspection
        if cancelled
        else inspect_all_disclosure_external_html_compress_payload(body)
    )
    return {
        "format": "finiq_disclosure_external_html_compress_repair_result_v1",
        "passed": not cancelled and not failed_modes and verification["passed"],
        "cancelled": cancelled,
        "inspected_failed_modes": inspection["failed_modes"],
        "target_mode_count": len(owner_modes),
        "regenerated_mode_count": len(results) - len(failed_modes),
        "failed_mode_count": len(failed_modes),
        "failed_modes": failed_modes,
        "results": results,
        "verification": verification,
    }


def _validate_derived_compression_owner_paths(
    body: dict[str, Any],
    *,
    input_directory: Path,
    output_directory: Path,
) -> dict[str, Any]:
    workspace = resolve_disclosure_workspace(body.get("data_root") or "")
    mode = validate_workspace_mode(body.get("mode"))
    parent_mode = validate_workspace_mode(body.get("parent_mode"))
    expected_input_directory = workspace.external_owner_mode(
        mode, parent_mode=parent_mode
    ).resolve()
    expected_output_directory = workspace.external_compress_owner_mode(
        mode, parent_mode=parent_mode
    ).resolve()
    if input_directory != expected_input_directory:
        raise ValueError(
            "derived filter compression must reuse its parent-owned input directory: "
            f"{expected_input_directory}"
        )
    if output_directory != expected_output_directory:
        raise ValueError(
            "derived filter compression must reuse its parent-owned output directory: "
            f"{expected_output_directory}"
        )
    return {
        "mode": mode,
        "parent_mode": parent_mode,
        "input_directory": expected_input_directory,
        "output_directory": expected_output_directory,
    }


def _validate_derived_compression_reuse(
    body: dict[str, Any],
    *,
    input_directory: Path,
    output_directory: Path,
) -> dict[str, Any]:
    owner = _validate_derived_compression_owner_paths(
        body,
        input_directory=input_directory,
        output_directory=output_directory,
    )
    mode = owner["mode"]
    parent_mode = owner["parent_mode"]
    expected_input_directory = owner["input_directory"]
    expected_output_directory = owner["output_directory"]

    source_json, _source_path = _load_workspace_filtered_payload(body)
    acpt_numbers = collect_acpt_numbers_from_json(source_json)
    _paths, integrity = _strictly_reuse_parent_html(
        output_directory=expected_input_directory,
        acpt_numbers=acpt_numbers,
        source_json=source_json,
    )
    compressed_path = expected_output_directory / COMPRESSED_EXTERNAL_HTML_FILENAME
    if not compressed_path.is_file():
        raise ValueError(
            "parent compressed external HTML does not exist: "
            f"{compressed_path}"
        )
    compressed_payload = json.loads(compressed_path.read_text(encoding="utf-8"))
    if (
        not isinstance(compressed_payload, dict)
        or compressed_payload.get("format")
        != "finiq_disclosure_external_html_docs_v1"
        or not isinstance(compressed_payload.get("records"), list)
    ):
        raise ValueError(
            "parent compressed external HTML has an invalid format: "
            f"{compressed_path}"
        )
    target_records: dict[str, dict[str, Any]] = {}
    target_set = set(acpt_numbers)
    for record in compressed_payload["records"]:
        if not isinstance(record, dict):
            continue
        acpt_no = str(record.get("acpt_no") or "").strip()
        if acpt_no not in target_set:
            continue
        if acpt_no in target_records:
            raise ValueError(
                "parent compressed external HTML has duplicate derived target: "
                f"{acpt_no}"
            )
        target_records[acpt_no] = record
    missing = [acpt_no for acpt_no in acpt_numbers if acpt_no not in target_records]
    if missing:
        raise ValueError(
            "parent compressed external HTML is missing derived targets: "
            + ", ".join(missing[:10])
        )
    verified_integrity = integrity["_verified_integrity_by_acpt_no"]
    mismatched = [
        acpt_no
        for acpt_no, record in target_records.items()
        if record.get("source_sha256")
        != verified_integrity[acpt_no]["source_sha256"]
        or record.get("source_size_bytes")
        != verified_integrity[acpt_no]["source_size_bytes"]
    ]
    if mismatched:
        raise ValueError(
            "parent compressed external HTML is stale for derived targets: "
            + ", ".join(mismatched[:10])
        )
    return {
        "mode": mode,
        "parent_mode": parent_mode,
        "acpt_numbers": acpt_numbers,
        "input_directory": expected_input_directory,
        "output_directory": expected_output_directory,
        "compressed_path": compressed_path,
    }


def _compression_source_integrity_problems(
    owner_state: dict[str, Any],
    acpt_numbers: list[str],
) -> dict[str, list[str] | str]:
    actual_integrity = owner_state["source_integrity_by_acpt_no"]
    invalid = set(owner_state["invalid_source_acpt_numbers"])
    unverified = set(owner_state["manifest_unverified_acpt_numbers"])
    mismatched = set(owner_state["manifest_mismatch_acpt_numbers"])
    return {
        "missing_or_invalid": [
            acpt_no
            for acpt_no in acpt_numbers
            if acpt_no in invalid or acpt_no not in actual_integrity
        ],
        "manifest_unverified": [
            acpt_no for acpt_no in acpt_numbers if acpt_no in unverified
        ],
        "manifest_mismatch": [
            acpt_no for acpt_no in acpt_numbers if acpt_no in mismatched
        ],
        "manifest_error": str(owner_state["manifest_error"] or ""),
    }


def _compression_record_source_mismatches(
    owner_state: dict[str, Any],
    acpt_numbers: list[str],
) -> list[str]:
    target_set = set(acpt_numbers)
    actual_integrity = owner_state["source_integrity_by_acpt_no"]
    return [
        acpt_no
        for record in owner_state["compressed_records"]
        if isinstance(record, dict)
        and (acpt_no := str(record.get("acpt_no") or "").strip()) in target_set
        and acpt_no in actual_integrity
        and (
            record.get("source_sha256")
            != actual_integrity[acpt_no]["source_sha256"]
            or record.get("source_size_bytes")
            != actual_integrity[acpt_no]["source_size_bytes"]
        )
    ]


def _inspect_derived_compression_reuse(
    body: dict[str, Any],
    *,
    input_directory: Path,
    output_directory: Path,
    owner_state: dict[str, Any],
) -> dict[str, Any]:
    owner = _validate_derived_compression_owner_paths(
        body,
        input_directory=input_directory,
        output_directory=output_directory,
    )
    source_json, _source_path = _load_workspace_filtered_payload(body)
    acpt_numbers = collect_acpt_numbers_from_json(source_json)
    compressed_path = output_directory / COMPRESSED_EXTERNAL_HTML_FILENAME
    if not owner_state["compressed_exists"]:
        raise ValueError(
            "parent compressed external HTML does not exist: "
            f"{compressed_path}"
        )
    if not owner_state["compressed_format_valid"]:
        raise ValueError(
            "parent compressed external HTML has an invalid format: "
            f"{compressed_path}"
        )

    target_records: dict[str, dict[str, Any]] = {}
    target_set = set(acpt_numbers)
    for record in owner_state["compressed_records"]:
        if not isinstance(record, dict):
            continue
        acpt_no = str(record.get("acpt_no") or "").strip()
        if acpt_no not in target_set:
            continue
        if acpt_no in target_records:
            raise ValueError(
                "parent compressed external HTML has duplicate derived target: "
                f"{acpt_no}"
            )
        target_records[acpt_no] = record
    missing = [acpt_no for acpt_no in acpt_numbers if acpt_no not in target_records]
    if missing:
        raise ValueError(
            "parent compressed external HTML is missing derived targets: "
            + ", ".join(missing[:10])
        )

    source_problems = _compression_source_integrity_problems(
        owner_state,
        acpt_numbers,
    )
    record_mismatches = _compression_record_source_mismatches(
        owner_state,
        acpt_numbers,
    )
    if (
        source_problems["missing_or_invalid"]
        or source_problems["manifest_unverified"]
        or source_problems["manifest_mismatch"]
        or source_problems["manifest_error"]
        or record_mismatches
    ):
        raise ValueError(
            "parent compressed external HTML source integrity check failed: "
            f"missing_or_invalid={source_problems['missing_or_invalid'][:10]}, "
            f"unverified={source_problems['manifest_unverified'][:10]}, "
            f"manifest_mismatch={source_problems['manifest_mismatch'][:10]}, "
            f"record_mismatch={record_mismatches[:10]}, "
            f"manifest_error={source_problems['manifest_error']}"
        )
    return {
        "mode": owner["mode"],
        "parent_mode": owner["parent_mode"],
        "acpt_numbers": acpt_numbers,
        "compressed_path": compressed_path,
    }


def inspect_disclosure_external_html_compress_payload(
    body: dict[str, Any],
    *,
    _owner_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify record membership and source integrity without rebuilding records.

    Existing-data inspection deliberately does not parse source HTML into compact
    records. Record extraction belongs to compression creation and its tests.
    """
    body = apply_workspace_defaults(
        "external_html_compress", body, create_workspace=False
    )
    input_directory_raw = str(body.get("input_directory") or "").strip()
    output_directory_raw = str(body.get("output_directory") or "").strip()
    if not input_directory_raw:
        raise ValueError("input_directory is required")
    if not output_directory_raw:
        raise ValueError("output_directory is required")

    input_directory = Path(input_directory_raw).expanduser().resolve()
    output_directory = Path(output_directory_raw).expanduser().resolve()
    compressed_path = output_directory / COMPRESSED_EXTERNAL_HTML_FILENAME

    def derived_failure(exc: Exception) -> dict[str, Any]:
        return {
            "format": "finiq_disclosure_external_html_compress_inspection_v1",
            "compressed_path": str(compressed_path),
            "passed": False,
            "skipped": False,
            "expected_records": 0,
            "verified_records": 0,
            "missing_records": 0,
            "unexpected_records": 0,
            "duplicate_records": 0,
            "missing_files": [],
            "invalid_files": [],
            "content_matches_source": False,
            "orphaned_output": False,
            "error": str(exc),
        }

    if body.get("parent_mode") not in (None, ""):
        try:
            _validate_derived_compression_owner_paths(
                body,
                input_directory=input_directory,
                output_directory=output_directory,
            )
        except Exception as exc:
            return derived_failure(exc)

    owner_state = _owner_state or _external_html_compression_owner_state(
        input_directory=input_directory,
        compressed_path=compressed_path,
    )
    expected_acpt_numbers = list(owner_state["expected_acpt_numbers"])
    if not expected_acpt_numbers:
        return _inspect_external_html_compression_without_source(
            compressed_path,
            compressed_exists=bool(owner_state["compressed_exists"]),
        )

    if body.get("parent_mode") not in (None, ""):
        try:
            derived = _inspect_derived_compression_reuse(
                body,
                input_directory=input_directory,
                output_directory=output_directory,
                owner_state=owner_state,
            )
        except Exception as exc:
            return derived_failure(exc)
        expected_records = len(derived["acpt_numbers"])
        return {
            "format": "finiq_disclosure_external_html_compress_inspection_v1",
            "compressed_path": str(derived["compressed_path"]),
            "passed": True,
            "skipped": expected_records == 0,
            "expected_records": expected_records,
            "verified_records": expected_records,
            "missing_records": 0,
            "unexpected_records": 0,
            "duplicate_records": 0,
            "missing_files": [],
            "invalid_files": [],
            "content_matches_source": True,
            "orphaned_output": False,
            "error": "",
        }
    verification = dict(owner_state["verification"])
    result = {
        "format": "finiq_disclosure_external_html_compress_inspection_v1",
        "compressed_path": str(compressed_path),
        **verification,
        "skipped": False,
        "orphaned_output": False,
        "content_matches_source": False,
        "error": "",
    }
    if not verification["passed"]:
        return result
    if not owner_state["compressed_format_valid"]:
        return {
            **result,
            "passed": False,
            "error": "압축 JSON 형식이 올바르지 않습니다.",
        }

    source_problems = _compression_source_integrity_problems(
        owner_state,
        expected_acpt_numbers,
    )
    record_mismatches = _compression_record_source_mismatches(
        owner_state,
        expected_acpt_numbers,
    )
    content_matches_source = not (
        source_problems["missing_or_invalid"]
        or source_problems["manifest_unverified"]
        or source_problems["manifest_mismatch"]
        or source_problems["manifest_error"]
        or record_mismatches
    )
    error = ""
    if not content_matches_source:
        error = (
            "외부 HTML 저장 무결성 또는 압축 record의 원문 hash·size가 "
            "일치하지 않습니다: "
            f"missing_or_invalid={source_problems['missing_or_invalid'][:10]}, "
            f"unverified={source_problems['manifest_unverified'][:10]}, "
            f"manifest_mismatch={source_problems['manifest_mismatch'][:10]}, "
            f"record_mismatch={record_mismatches[:10]}, "
            f"manifest_error={source_problems['manifest_error']}"
        )
    return {
        **result,
        "passed": content_matches_source,
        "content_matches_source": content_matches_source,
        "error": error,
    }


def compress_disclosure_external_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: Callable[[], bool] | None = None,
    *,
    _metadata_payload: Any = _REQUEST_METADATA,
) -> dict[str, Any]:
    """Extract compact metadata from downloaded KIND external HTML files into one JSON."""
    def ensure_not_cancelled() -> None:
        if cancel_check is not None and cancel_check():
            raise InterruptedError("external HTML compression cancelled")

    ensure_not_cancelled()
    if "source_directory" in body:
        raise ValueError(
            "source_directory is not supported; use input_directory"
        )
    body = apply_workspace_defaults("external_html_compress", body)
    input_directory_raw = str(body.get("input_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    progress_interval = _parse_progress_interval(body.get("progress_interval"))
    output_directory_raw = str(body.get("output_directory") or "").strip()
    if not output_directory_raw:
        raise ValueError("output_directory is required")
    output_directory = Path(output_directory_raw).expanduser().resolve()

    if body.get("parent_mode") not in (None, ""):
        ensure_not_cancelled()
        derived = _validate_derived_compression_reuse(
            body,
            input_directory=input_directory,
            output_directory=output_directory,
        )
        mode = derived["mode"]
        parent_mode = derived["parent_mode"]
        acpt_numbers = derived["acpt_numbers"]
        ensure_not_cancelled()
        return {
            "format": "finiq_disclosure_external_html_compress_result_v1",
            "mode": mode,
            "parent_mode": parent_mode,
            "reused_parent_compressed_html": True,
            "input_directory": str(derived["input_directory"]),
            "output_directory": str(derived["output_directory"]),
            "summary": {
                "found_files": len(acpt_numbers),
                "compressed_files": len(acpt_numbers),
                "written_files": 0,
            },
            "written_files": [],
            "verification": {
                "passed": True,
                "expected_records": len(acpt_numbers),
                "verified_records": len(acpt_numbers),
                "missing_records": 0,
            },
            "progress_log": [
                f"부모 필터 {parent_mode}의 외부 HTML 압축 결과 "
                f"{len(acpt_numbers)}건을 재사용했습니다."
            ],
        }

    progress_log: deque[str] = deque(maxlen=100)

    def emit(message: str) -> None:
        progress_log.append(message)
        if progress_callback is not None:
            progress_callback(message)

    html_files = _collect_yearly_html_files(input_directory)
    if not html_files:
        msg = "No external HTML files found in input_directory"
        raise ValueError(msg)

    manifest_path = input_directory / HTML_MANIFEST_FILENAME
    if _metadata_payload is not _REQUEST_METADATA:
        metadata_payload = _metadata_payload
        metadata_source = "current filtered disclosure"
    elif body.get("data_root") not in (None, ""):
        metadata_payload, _metadata_path = _load_workspace_filtered_payload(body)
        metadata_source = "current filtered disclosure"
    else:
        metadata_payload: Any = None
        if manifest_path.is_file():
            metadata_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        metadata_source = "manifest"
    metadata = _collect_disclosure_metadata_from_json(metadata_payload)
    expected_acpt_numbers = [html_path.stem for _year, html_path in html_files]
    missing_metadata_acpt_numbers = [
        acpt_no for acpt_no in expected_acpt_numbers if acpt_no not in metadata
    ]
    metadata_check = {
        "complete": not missing_metadata_acpt_numbers,
        "expected_records": len(expected_acpt_numbers),
        "matched_records": len(expected_acpt_numbers)
        - len(missing_metadata_acpt_numbers),
        "missing_records": len(missing_metadata_acpt_numbers),
    }
    if missing_metadata_acpt_numbers:
        sample = ", ".join(missing_metadata_acpt_numbers[:10])
        raise ValueError(
            f"{metadata_source}에서 외부 HTML {len(html_files)}건 중 "
            f"{len(missing_metadata_acpt_numbers)}건의 metadata를 찾지 못했습니다. "
            f"누락 접수번호 예시: {sample}"
        )
    for year, html_path in html_files:
        acpt_no = html_path.stem
        metadata_year = _year_from_disclosure(acpt_no, metadata[acpt_no])
        if year != metadata_year:
            raise ValueError(
                f"external HTML year does not match disclosed_at: "
                f"{html_path} expected={metadata_year}"
            )

    worker_count = _external_html_compress_workers(body, len(html_files))

    emit(f"외부 HTML 압축 대상 {len(html_files)}건을 찾았습니다.")
    emit(f"입력 경로: {input_directory}")
    emit(f"병렬 처리: {worker_count}개 워커")

    indexed_records: list[tuple[str, str, dict[str, Any]] | None] = [None] * len(
        html_files
    )
    if worker_count == 1:
        for args in (
            (index, year, html_path)
            for index, (year, html_path) in enumerate(html_files)
        ):
            ensure_not_cancelled()
            index, year, acpt_no, record = _compress_external_html_file(args)
            ensure_not_cancelled()
            expected_acpt_no = html_files[index][1].stem
            record["metadata"] = metadata[expected_acpt_no]
            record["title"] = str(metadata[expected_acpt_no].get("title") or "")
            indexed_records[index] = (year, acpt_no, record)
            completed_count = index + 1
            if completed_count % progress_interval == 0:
                emit(
                    f"외부 HTML 압축 중간 확인: {completed_count}/{len(html_files)}건 처리."
                )
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            items = (
                (index, year, html_path)
                for index, (year, html_path) in enumerate(html_files)
            )
            completed = bounded_as_completed(
                executor,
                items,
                lambda item: executor.submit(_compress_external_html_file, item),
                max_pending=worker_count * 2,
            )
            for completed_count, (future, _item) in enumerate(completed, start=1):
                ensure_not_cancelled()
                index, year, acpt_no, record = future.result()
                ensure_not_cancelled()
                expected_acpt_no = html_files[index][1].stem
                record["metadata"] = metadata[expected_acpt_no]
                record["title"] = str(metadata[expected_acpt_no].get("title") or "")
                indexed_records[index] = (year, acpt_no, record)
                if completed_count % progress_interval == 0:
                    emit(
                        f"외부 HTML 압축 중간 확인: {completed_count}/{len(html_files)}건 처리."
                    )

    missing_worker_indexes = [
        index
        for index, indexed_record in enumerate(indexed_records)
        if indexed_record is None
    ]
    processing_verification = {
        "passed": not missing_worker_indexes,
        "expected_files": len(html_files),
        "processed_files": len(html_files) - len(missing_worker_indexes),
        "missing_files": len(missing_worker_indexes),
        "missing_indexes": missing_worker_indexes,
    }
    if missing_worker_indexes:
        msg = f"External HTML compression worker results are incomplete: missing indexes {missing_worker_indexes[:10]}"
        raise ValueError(msg)
    emit(
        "외부 HTML 압축 병렬 결과 확인: "
        f"{processing_verification['processed_files']}/{processing_verification['expected_files']}건 처리."
    )
    records: list[dict[str, Any]] = []
    for indexed_record in indexed_records:
        assert indexed_record is not None
        _year, _acpt_no, record = indexed_record
        records.append(record)
    indexed_records.clear()

    written_files: list[str] = []
    output_path = output_directory / "compressed-external-html.json"
    payload = {
        "format": "finiq_disclosure_external_html_docs_v1",
        "summary": {"found_files": len(html_files), "compressed_files": len(records)},
        "records": records,
    }
    actual_acpt_numbers = [str(record.get("acpt_no") or "") for record in records]
    if (
        len(set(expected_acpt_numbers)) != len(expected_acpt_numbers)
        or len(set(actual_acpt_numbers)) != len(actual_acpt_numbers)
        or set(actual_acpt_numbers) != set(expected_acpt_numbers)
    ):
        raise ValueError(
            "External HTML compression membership does not match input filenames"
        )
    _validate_external_html_manifest_integrity(
        input_directory=input_directory,
        records=records,
    )
    ensure_not_cancelled()
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    cleanup_warnings: list[str] = []
    staging_directory = Path(
        tempfile.mkdtemp(
            prefix=".finiq-external-html-compress-",
            dir=output_directory.parent,
        )
    )
    try:
        staged_path = staging_directory / output_path.name
        atomic_write_json(staged_path, payload)
        verification = _verify_compressed_external_html_files(
            written_files=[str(staged_path)],
            expected_acpt_numbers=expected_acpt_numbers,
        )
        if not verification["passed"]:
            raise ValueError("External HTML compression verification failed")
        ensure_not_cancelled()
        output_directory.mkdir(parents=True, exist_ok=True)
        os.replace(staged_path, output_path)
    except Exception:
        try:
            shutil.rmtree(staging_directory)
        except OSError:
            pass
        raise
    try:
        shutil.rmtree(staging_directory)
    except OSError as exc:
        warning = (
            "외부 HTML 압축 JSON 게시에는 성공했지만 준비 디렉터리를 "
            f"정리하지 못했습니다: {staging_directory} ({exc})"
        )
        cleanup_warnings.append(warning)
        emit(warning)
    written_files.append(str(output_path))
    emit(f"외부 HTML 압축 JSON 저장 완료: {output_path}")
    emit(
        "외부 HTML 압축 결과 재검사: "
        f"{verification['verified_records']}/{verification['expected_records']}건 확인, "
        f"누락 {verification['missing_records']}건."
    )

    return {
        "format": "finiq_disclosure_external_html_compress_result_v1",
        "input_directory": str(input_directory),
        "output_directory": str(output_directory),
        "summary": {
            "found_files": len(html_files),
            "compressed_files": len(records),
            "written_files": len(written_files),
        },
        "written_files": written_files,
        "metadata_check": metadata_check,
        "processing_verification": processing_verification,
        "verification": verification,
        "cleanup_warnings": cleanup_warnings,
        "progress_log": list(progress_log),
    }
