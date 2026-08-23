"""Compressed external disclosure HTML payload helpers."""

from __future__ import annotations

from collections import deque
import tempfile

from finiq.concurrency import bounded_as_completed
from finiq.market_desk.web.features.disclosure_workflow.layout import atomic_write_json
from finiq.market_desk.web.features.disclosures.html_common import *


def inspect_disclosure_external_html_compress_payload(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Verify the saved compressed JSON against the current filter and source HTML."""
    input_directory_raw = str(body.get("input_directory") or "").strip()
    output_directory_raw = str(body.get("output_directory") or "").strip()
    if not input_directory_raw:
        raise ValueError("input_directory is required")
    if not output_directory_raw:
        raise ValueError("output_directory is required")

    input_directory = Path(input_directory_raw).expanduser().resolve()
    output_directory = Path(output_directory_raw).expanduser().resolve()
    compressed_path = output_directory / COMPRESSED_EXTERNAL_HTML_FILENAME
    source_json, _source_path = _load_workspace_filtered_payload(body)
    expected_acpt_numbers = collect_acpt_numbers_from_json(source_json)

    if body.get("parent_mode") not in (None, ""):
        try:
            compress_disclosure_external_html_payload(body)
        except Exception as exc:
            return {
                "format": "finiq_disclosure_external_html_compress_inspection_v1",
                "compressed_path": str(compressed_path),
                "passed": False,
                "expected_records": len(expected_acpt_numbers),
                "verified_records": 0,
                "missing_records": len(expected_acpt_numbers),
                "unexpected_records": 0,
                "duplicate_records": 0,
                "missing_files": [] if compressed_path.is_file() else [str(compressed_path)],
                "invalid_files": [],
                "missing_acpt_numbers": [],
                "unexpected_acpt_numbers": [],
                "duplicate_acpt_numbers": [],
                "content_matches_source": False,
                "error": str(exc),
            }
        return {
            "format": "finiq_disclosure_external_html_compress_inspection_v1",
            "compressed_path": str(compressed_path),
            "passed": True,
            "expected_records": len(expected_acpt_numbers),
            "verified_records": len(expected_acpt_numbers),
            "missing_records": 0,
            "unexpected_records": 0,
            "duplicate_records": 0,
            "missing_files": [],
            "invalid_files": [],
            "missing_acpt_numbers": [],
            "unexpected_acpt_numbers": [],
            "duplicate_acpt_numbers": [],
            "content_matches_source": True,
            "error": "",
        }

    verification = _verify_compressed_external_html_files(
        written_files=[str(compressed_path)],
        expected_acpt_numbers=expected_acpt_numbers,
    )
    result = {
        "format": "finiq_disclosure_external_html_compress_inspection_v1",
        "compressed_path": str(compressed_path),
        **verification,
        "content_matches_source": False,
        "error": "",
    }
    if not verification["passed"]:
        return result

    try:
        saved_payload = json.loads(compressed_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {**result, "passed": False, "error": str(exc)}
    if (
        not isinstance(saved_payload, dict)
        or saved_payload.get("format")
        != "finiq_disclosure_external_html_docs_v1"
        or not isinstance(saved_payload.get("records"), list)
    ):
        return {
            **result,
            "passed": False,
            "error": "압축 JSON 형식이 올바르지 않습니다.",
        }

    if not expected_acpt_numbers:
        empty_payload = {
            "format": "finiq_disclosure_external_html_docs_v1",
            "summary": {"found_files": 0, "compressed_files": 0},
            "records": [],
        }
        content_matches_source = saved_payload == empty_payload
        return {
            **result,
            "passed": content_matches_source,
            "content_matches_source": content_matches_source,
            "error": "" if content_matches_source else "빈 필터의 압축 JSON 내용이 올바르지 않습니다.",
        }

    try:
        with tempfile.TemporaryDirectory(prefix="finiq-compress-inspection-") as temporary:
            compress_disclosure_external_html_payload(
                {
                    "input_directory": str(input_directory),
                    "output_directory": temporary,
                    "parallel_workers": body.get("parallel_workers"),
                }
            )
            rebuilt_payload = json.loads(
                (Path(temporary) / COMPRESSED_EXTERNAL_HTML_FILENAME).read_text(
                    encoding="utf-8"
                )
            )
    except Exception as exc:
        return {**result, "passed": False, "error": str(exc)}

    content_matches_source = saved_payload == rebuilt_payload
    return {
        **result,
        "passed": content_matches_source,
        "content_matches_source": content_matches_source,
        "error": "" if content_matches_source else "압축 JSON이 현재 원문에서 다시 계산한 결과와 다릅니다.",
    }


def compress_disclosure_external_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Extract compact metadata from downloaded KIND external HTML files into one JSON."""
    if "source_directory" in body:
        raise ValueError(
            "source_directory is not supported; use input_directory"
        )
    input_directory_raw = str(body.get("input_directory") or "").strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    limit = _parse_merge_limit(body.get("limit"))
    output_directory_raw = str(body.get("output_directory") or "").strip()
    output_directory = (
        Path(output_directory_raw).expanduser().resolve()
        if output_directory_raw
        else input_directory
    )

    if body.get("parent_mode") not in (None, ""):
        workspace = resolve_disclosure_workspace(body.get("data_root") or "")
        mode = validate_workspace_mode(body.get("mode"))
        parent_mode = validate_workspace_mode(body.get("parent_mode"))
        expected_directory = workspace.external_owner_mode(
            mode, parent_mode=parent_mode
        ).resolve()
        if (
            input_directory != expected_directory
            or output_directory != expected_directory
        ):
            raise ValueError(
                "derived filter compression must reuse its parent-owned directory: "
                f"{expected_directory}"
            )
        source_json, _source_path = _load_workspace_filtered_payload(body)
        acpt_numbers = collect_acpt_numbers_from_json(source_json)
        _paths, integrity = _strictly_reuse_parent_html(
            output_directory=expected_directory,
            acpt_numbers=acpt_numbers,
            source_json=source_json,
        )
        compressed_path = expected_directory / COMPRESSED_EXTERNAL_HTML_FILENAME
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
        for index, record in enumerate(compressed_payload["records"]):
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
            "format": "finiq_disclosure_external_html_compress_result_v1",
            "mode": mode,
            "parent_mode": parent_mode,
            "reused_parent_compressed_html": True,
            "input_directory": str(expected_directory),
            "output_directory": str(expected_directory),
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
    if limit is not None:
        html_files = html_files[:limit]
    if not html_files:
        msg = "No external HTML files found in input_directory"
        raise ValueError(msg)

    manifest_path = input_directory / HTML_MANIFEST_FILENAME
    manifest_payload: Any = None
    if manifest_path.is_file():
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata = _collect_disclosure_metadata_from_json(manifest_payload)
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
            f"manifest에서 외부 HTML {len(html_files)}건 중 "
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
            index, year, acpt_no, record = _compress_external_html_file(args)
            expected_acpt_no = html_files[index][1].stem
            record["metadata"] = metadata[expected_acpt_no]
            record["title"] = str(metadata[expected_acpt_no].get("title") or "")
            indexed_records[index] = (year, acpt_no, record)
            completed_count = index + 1
            if completed_count % 100 == 0:
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
                index, year, acpt_no, record = future.result()
                expected_acpt_no = html_files[index][1].stem
                record["metadata"] = metadata[expected_acpt_no]
                record["title"] = str(metadata[expected_acpt_no].get("title") or "")
                indexed_records[index] = (year, acpt_no, record)
                if completed_count % 100 == 0:
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
    output_directory.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_path, payload)
    written_files.append(str(output_path))
    emit(f"외부 HTML 압축 JSON 저장 완료: {output_path}")

    verification = _verify_compressed_external_html_files(
        written_files=written_files,
        expected_acpt_numbers=expected_acpt_numbers,
    )
    if not verification["passed"]:
        raise ValueError("External HTML compression verification failed")
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
        "progress_log": list(progress_log),
    }
