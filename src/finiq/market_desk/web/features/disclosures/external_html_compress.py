"""Compressed external disclosure HTML payload helpers."""

from __future__ import annotations

from finiq.concurrency import bounded_as_completed
from finiq.market_desk.web.features.disclosure_workflow.layout import atomic_write_json
from finiq.market_desk.web.features.disclosures.html_common import *


def compress_disclosure_external_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Extract compact metadata from downloaded KIND external HTML files into one JSON."""
    input_directory_raw = str(
        body.get("input_directory") or body.get("source_directory") or ""
    ).strip()
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

    progress_log: list[str] = []

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
        "progress_log": progress_log[-100:],
    }
