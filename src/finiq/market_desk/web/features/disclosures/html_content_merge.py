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
    limit = _parse_merge_limit(body.get("limit"))
    output_directory = _resolve_content_merge_output_directory(
        str(body.get("output_directory") or "").strip(), input_directory
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
        msg = "No content HTML files found in input_directory"
        raise ValueError(msg)

    emit(f"내부 HTML 병합 대상 {len(html_files)}건을 찾았습니다.")
    emit(f"입력 경로: {input_directory}")

    records_by_year: dict[str, list[dict[str, Any]]] = {}
    for index, (year, html_path) in enumerate(html_files, start=1):
        records_by_year.setdefault(year, []).append(
            {
                "acpt_no": html_path.stem,
                "source_file": str(html_path.resolve()),
                "html": html_path.read_text(encoding="utf-8"),
            }
        )
        if index % 100 == 0:
            emit(f"내부 HTML 병합 중간 확인: {index}/{len(html_files)}건 처리.")

    written_files: list[str] = []
    output_directory.mkdir(parents=True, exist_ok=True)
    for year, records in sorted(records_by_year.items()):
        year_output_path = output_directory / f"merged-content-html-{year}.json"
        payload = {
            "format": "finiq_disclosure_content_html_merge_v1",
            "input_directory": str(input_directory),
            "output_path": str(year_output_path),
            "year": year,
            "summary": {"found_files": len(records), "merged_files": len(records)},
            "records": records,
        }
        year_output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        written_files.append(str(year_output_path))
        emit(f"연도별 JSON 저장 완료: {year_output_path}")

    return {
        "format": "finiq_disclosure_content_html_merge_result_v1",
        "input_directory": str(input_directory),
        "output_directory": str(output_directory),
        "summary": {
            "found_files": len(html_files),
            "merged_files": len(html_files),
            "written_files": len(written_files),
        },
        "written_files": written_files,
        "progress_log": progress_log[-100:],
    }
