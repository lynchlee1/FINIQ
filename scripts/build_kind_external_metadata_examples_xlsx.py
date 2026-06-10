from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from finiq.market_desk.web.disclosure_html import compress_disclosure_external_html_payload


SAVE_REASONS = {
    "records[].acpt_no": "공시별 접수번호",
    "records[].title": "공시별 제목",
    "records[].header": "공시별 회사/헤더",
    "records[].selected_main_doc_no": "선택 본문 문서번호",
    "records[].attached_docs": "첨부 문서번호",
    "records[].metadata": "원천 공시 행 메타데이터",
    "records[].external_metadata.selects": "문서 선택값",
    "records[].external_metadata.scripts[].variables": "compact script variables",
    "records[].external_metadata.text_blocks": "공시별 상태/정정 안내 가능성",
    "records[].external_metadata.script_variables": "flattened script variables",
    "records[].external_metadata.source_sha256": "원본 무결성",
    "records[].external_metadata.source_size_bytes": "원본 크기 검증",
}

DISCARD_REASONS = {
    "records[].external_metadata.meta": "대부분 KIND 정적 페이지 메타",
    "records[].main_docs": "external_metadata.selects의 mainDoc에서 재구성 가능",
    "records[].external_metadata.forms[].attrs": "대부분 정적 form shell",
    "records[].external_metadata.forms[].textareas": "대부분 없음 또는 정적 UI",
    "records[].external_metadata.forms[].buttons": "대부분 반복 버튼",
    "records[].external_metadata.inputs": "대부분 상위 핵심 필드와 중복",
    "records[].external_metadata.links": "대부분 반복 viewer control",
    "records[].external_metadata.frames": "대부분 정적 frame shell",
    "records[].external_metadata.resources": "대부분 반복 static asset",
    "records[].external_metadata.scripts[].attrs": "대부분 공통 script src/version",
    "records[].external_metadata.scripts[].text": "큰 반복 viewer logic",
}


def _xlsx_column_name(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _preview(value: Any) -> str:
    return _cell(value).strip()


def _sheet_xml(rows: list[list[Any]], widths: list[int]) -> str:
    max_cols = max((len(row) for row in rows), default=1)
    max_rows = max(1, len(rows))
    sheet_rows_xml: list[str] = []
    for row_number, row_values in enumerate(rows, start=1):
        cell_xml: list[str] = []
        for column_number, value in enumerate(row_values, start=1):
            cell_ref = f"{_xlsx_column_name(column_number)}{row_number}"
            cell_xml.append(
                f'<c r="{cell_ref}" t="inlineStr"><is><t>{escape(_cell(value))}</t></is></c>'
            )
        sheet_rows_xml.append(f'<row r="{row_number}">{"".join(cell_xml)}</row>')

    dimension_ref = f"A1:{_xlsx_column_name(max_cols)}{max_rows}"
    col_xml = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths[:max_cols], start=1)
    )
    if len(widths) < max_cols:
        col_xml += "".join(
            f'<col min="{index}" max="{index}" width="24" customWidth="1"/>'
            for index in range(len(widths) + 1, max_cols + 1)
        )

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimension_ref}"/>'
        '<sheetViews><sheetView workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f"<cols>{col_xml}</cols>"
        f'<sheetData>{"".join(sheet_rows_xml)}</sheetData>'
        f'<autoFilter ref="{dimension_ref}"/>'
        "</worksheet>"
    )


def _workbook_bytes(sheets: list[tuple[str, list[list[Any]], list[int]]]) -> bytes:
    sheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index, _sheet in enumerate(sheets, start=1)
    )
    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{sheet_overrides}"
        "</Types>"
    )
    root_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
            for index, _sheet in enumerate(sheets, start=1)
        )
        + "</Relationships>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        + "".join(
            f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
            for index, (name, _rows, _widths) in enumerate(sheets, start=1)
        )
        + "</sheets></workbook>"
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        for index, (_name, rows, widths) in enumerate(sheets, start=1):
            zf.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(rows, widths))
    return output.getvalue()


def _summary_rows(records: list[dict[str, Any]]) -> list[list[Any]]:
    rows = [
        [
            "acpt_no",
            "title",
            "header",
            "selected_main_doc_no",
            "main_docs",
            "attached_docs",
            "inputs",
            "selects",
            "text_blocks",
            "script_variables",
            "source_size_bytes",
            "source_file",
        ]
    ]
    for record in records:
        external = record.get("external_metadata") or {}
        rows.append(
            [
                record.get("acpt_no"),
                record.get("title"),
                record.get("header"),
                record.get("selected_main_doc_no"),
                len(record.get("main_docs") or []),
                len(record.get("attached_docs") or []),
                len(external.get("inputs") or []),
                len(external.get("selects") or []),
                len(external.get("text_blocks") or []),
                len(external.get("script_variables") or []),
                external.get("source_size_bytes"),
                record.get("source_file"),
            ]
        )
    return rows


def _save_rows(records: list[dict[str, Any]]) -> list[list[Any]]:
    rows = [["acpt_no", "field_path", "reason", "value"]]
    for record in records:
        external = record.get("external_metadata") or {}
        values = {
            "records[].acpt_no": record.get("acpt_no"),
            "records[].title": record.get("title"),
            "records[].header": record.get("header"),
            "records[].selected_main_doc_no": record.get("selected_main_doc_no"),
            "records[].attached_docs": record.get("attached_docs"),
            "records[].metadata": record.get("metadata"),
            "records[].external_metadata.selects": external.get("selects"),
            "records[].external_metadata.scripts[].variables": [
                script.get("variables")
                for script in external.get("scripts") or []
                if script.get("variables")
            ],
            "records[].external_metadata.text_blocks": external.get("text_blocks"),
            "records[].external_metadata.script_variables": external.get("script_variables"),
            "records[].external_metadata.source_sha256": external.get("source_sha256"),
            "records[].external_metadata.source_size_bytes": external.get("source_size_bytes"),
        }
        for field_path, reason in SAVE_REASONS.items():
            rows.append([record.get("acpt_no"), field_path, reason, _preview(values.get(field_path))])
    return rows


def _discard_rows(records: list[dict[str, Any]]) -> list[list[Any]]:
    rows = [["acpt_no", "field_path", "reason", "value"]]
    for record in records:
        external = record.get("external_metadata") or {}
        form_attrs = [form.get("attrs") for form in external.get("forms") or []]
        form_textareas = [form.get("textareas") for form in external.get("forms") or [] if form.get("textareas")]
        form_buttons = [form.get("buttons") for form in external.get("forms") or [] if form.get("buttons")]
        script_attrs = [script.get("attrs") for script in external.get("scripts") or []]
        script_text = [script.get("text") for script in external.get("scripts") or [] if script.get("text")]
        values = {
            "records[].external_metadata.meta": external.get("meta"),
            "records[].main_docs": record.get("main_docs"),
            "records[].external_metadata.forms[].attrs": form_attrs,
            "records[].external_metadata.forms[].textareas": form_textareas,
            "records[].external_metadata.forms[].buttons": form_buttons,
            "records[].external_metadata.inputs": external.get("inputs"),
            "records[].external_metadata.links": external.get("links"),
            "records[].external_metadata.frames": external.get("frames"),
            "records[].external_metadata.resources": external.get("resources"),
            "records[].external_metadata.scripts[].attrs": script_attrs,
            "records[].external_metadata.scripts[].text": script_text,
        }
        for field_path, reason in DISCARD_REASONS.items():
            rows.append([record.get("acpt_no"), field_path, reason, _preview(values.get(field_path))])
    return rows


def _field_count_rows(records: list[dict[str, Any]]) -> list[list[Any]]:
    rows = [["acpt_no", "field", "count"]]
    count_fields = [
        "meta",
        "forms",
        "inputs",
        "selects",
        "links",
        "frames",
        "resources",
        "scripts",
        "text_blocks",
        "script_variables",
    ]
    for record in records:
        external = record.get("external_metadata") or {}
        for field in count_fields:
            rows.append([record.get("acpt_no"), field, len(external.get(field) or [])])
    return rows


def build_examples_xlsx(input_directory: Path, output_path: Path, limit: int | None) -> dict[str, Any]:
    temp_directory = output_path.parent / ".kind_external_metadata_examples_tmp"
    if temp_directory.exists():
        shutil.rmtree(temp_directory)
    result = compress_disclosure_external_html_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(temp_directory),
            "limit": limit,
        }
    )
    compressed_path = Path(result["written_files"][0])
    payload = json.loads(compressed_path.read_text(encoding="utf-8"))
    records = list(payload.get("records") or [])

    sheets = [
        ("Summary", _summary_rows(records), [16, 42, 28, 22, 12, 14, 10, 10, 12, 16, 16, 60]),
        ("Save Examples", _save_rows(records), [16, 46, 34, 80]),
        ("Discard Examples", _discard_rows(records), [16, 48, 34, 80]),
        ("Field Counts", _field_count_rows(records), [16, 24, 10]),
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(_workbook_bytes(sheets))
    shutil.rmtree(temp_directory)
    return {
        "output_path": str(output_path),
        "records": len(records),
        "source": str(input_directory),
        "verification": result.get("verification"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build KIND external metadata example workbook.")
    parser.add_argument("--input-directory", default=str(PROJECT_ROOT / "samples" / "kind_html"))
    parser.add_argument("--output", default=str(PROJECT_ROOT / "scripts" / "kind_external_metadata_examples.xlsx"))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    result = build_examples_xlsx(
        Path(args.input_directory).expanduser().resolve(),
        Path(args.output).expanduser().resolve(),
        args.limit,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
