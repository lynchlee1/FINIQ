"""Disclosure parse XLSX export helpers."""

from __future__ import annotations

from finiq.market_desk.web.features.disclosures.html_parse_support import *

def _xlsx_column_name(index: int) -> str:
    result = ""
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result = chr(65 + remainder) + result
    return result


def build_parse_export_xlsx(
    output_path_raw: str, requested_mode: str, latest_only: bool = False
) -> bytes:
    from xml.sax.saxutils import escape

    output_path = _resolve_parse_result_path(
        Path(output_path_raw).expanduser().resolve(), requested_mode
    )
    try:
        payload = _load_parse_payload(output_path)
    except Exception as exc:
        raise ValueError(
            f"파싱 결과 파일을 찾을 수 없습니다: {output_path.name}"
        ) from exc

    records = [
        _compact_record(record) if isinstance(record, dict) else record
        for record in list(payload.get("records") or [])
    ]
    if latest_only:
        filtered_records = []
        for record in records:
            family_id, current_sequence, member_count = _record_family_info(record)
            if family_id and member_count is not None and current_sequence is not None:
                if current_sequence == member_count - 1:
                    filtered_records.append(record)
            else:
                filtered_records.append(record)
        records = filtered_records

    # Dynamic extraction of all keys
    all_keys = set()
    for record in records:
        all_keys.update(record.keys())

    # Priority headers
    priority = ["title", "acpt_no", "source_file"]
    headers = [p for p in priority if p in all_keys] + sorted(
        k
        for k in all_keys
        if k not in priority and k != "correction_families" and k != "source_lines"
    )

    workbook_rows = [headers]
    for record in records:
        row = []
        for header in headers:
            val = record.get(header)
            if isinstance(val, (list, dict)):
                row.append(json.dumps(val, ensure_ascii=False))
            elif val is None:
                row.append("")
            else:
                row.append(str(val))
        workbook_rows.append(row)

    sheet_rows_xml: list[str] = []
    for row_number, row_values in enumerate(workbook_rows, start=1):
        cell_xml: list[str] = []
        for column_number, value in enumerate(row_values, start=1):
            cell_ref = f"{_xlsx_column_name(column_number)}{row_number}"
            cell_xml.append(
                f'<c r="{cell_ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>'
            )
        sheet_rows_xml.append(f'<row r="{row_number}">{"".join(cell_xml)}</row>')

    dimension_ref = f"A1:{_xlsx_column_name(len(headers))}{max(1, len(workbook_rows))}"

    col_widths = "".join(
        f'<col min="{i}" max="{i}" width="20" customWidth="1"/>'
        for i in range(1, len(headers) + 1)
    )

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dimension_ref}"/>'
        '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
        '<sheetFormatPr defaultRowHeight="15"/>'
        f"<cols>{col_widths}</cols>"
        f"<sheetData>{''.join(sheet_rows_xml)}</sheetData>"
        f'<autoFilter ref="{dimension_ref}"/>'
        "</worksheet>"
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
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
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        "</Relationships>"
    )

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )

    import io
    import zipfile

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types_xml)
        zf.writestr("_rels/.rels", root_rels_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    return output.getvalue()


__all__ = [name for name in globals() if not name.startswith("__")]
