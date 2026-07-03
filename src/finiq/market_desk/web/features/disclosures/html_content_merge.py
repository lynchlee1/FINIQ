"""Disclosure content HTML merge payload helpers."""

from __future__ import annotations

from finiq.market_desk.web.features.disclosures.html_common import *

def merge_disclosure_content_html_payload(
    body: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Merge downloaded KIND content HTML files into JSON."""
    input_directory_raw = str(
        body.get("input_directory") or body.get("source_directory") or ""
    ).strip()
    if not input_directory_raw:
        msg = "input_directory is required"
        raise ValueError(msg)
    input_directory = Path(input_directory_raw).expanduser().resolve()
    input_split_by_year = _as_input_split_by_year(body)
    output_split_by_year = _as_output_split_by_year(body)
    limit = _parse_merge_limit(body.get("limit"))
    output_path = _resolve_content_merge_output_path(
        str(body.get("output_path") or "").strip(), input_directory
    )
    output_root = (
        output_path.parent if output_path.suffix.lower() == ".json" else output_path
    )

    progress_log: list[str] = []

    def emit(message: str) -> None:
        progress_log.append(message)
        if progress_callback is not None:
            progress_callback(message)

    html_files = _collect_content_html_files(
        input_directory, split_by_year=input_split_by_year
    )
    if limit is not None:
        html_files = html_files[:limit]
    if not html_files:
        msg = "No content HTML files found in input_directory"
        raise ValueError(msg)

    emit(f"내부 HTML 병합 대상 {len(html_files)}건을 찾았습니다.")
    emit(f"입력 경로: {input_directory}")
    emit(f"입력 분할저장: {'예' if input_split_by_year else '아니오'}")
    emit(f"출력 분할저장: {'예' if output_split_by_year else '아니오'}")

    records_by_year: dict[str, list[dict[str, Any]]] = {}
    for index, (year, html_path) in enumerate(html_files, start=1):
        records_by_year.setdefault(year, []).append(
            {
                "acpt_no": html_path.stem,
                "source_file": str(html_path.resolve()),
                "html": html_path.read_text(encoding="utf-8", errors="replace"),
            }
        )
        if index % 100 == 0:
            emit(f"내부 HTML 병합 중간 확인: {index}/{len(html_files)}건 처리.")

    written_files: list[str] = []
    if output_split_by_year:
        output_root.mkdir(parents=True, exist_ok=True)
        for year, records in sorted(records_by_year.items()):
            year_output_path = output_root / f"merged-content-html-{year}.json"
            payload = {
                "format": "finiq_disclosure_content_html_merge_v1",
                "input_directory": str(input_directory),
                "output_path": str(year_output_path),
                "split_by_year": True,
                "input_split_by_year": input_split_by_year,
                "output_split_by_year": True,
                "year": year,
                "summary": {"found_files": len(records), "merged_files": len(records)},
                "records": records,
            }
            year_output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            written_files.append(str(year_output_path))
            emit(f"연도별 JSON 저장 완료: {year_output_path}")
    else:
        records = [
            record
            for year in sorted(records_by_year)
            for record in records_by_year[year]
        ]
        payload = {
            "format": "finiq_disclosure_content_html_merge_v1",
            "input_directory": str(input_directory),
            "output_path": str(output_path),
            "split_by_year": False,
            "input_split_by_year": input_split_by_year,
            "output_split_by_year": False,
            "summary": {"found_files": len(records), "merged_files": len(records)},
            "records": records,
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        written_files.append(str(output_path))
        emit(f"내부 HTML 병합 JSON 저장 완료: {output_path}")

    return {
        "format": "finiq_disclosure_content_html_merge_result_v1",
        "input_directory": str(input_directory),
        "output_path": str(output_path),
        "split_by_year": output_split_by_year,
        "input_split_by_year": input_split_by_year,
        "output_split_by_year": output_split_by_year,
        "summary": {
            "found_files": len(html_files),
            "merged_files": len(html_files),
            "written_files": len(written_files),
        },
        "written_files": written_files,
        "progress_log": progress_log[-100:],
    }


