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
    "records[].acpt_no": "파일명/뷰어 hidden input에서 온 KIND 접수번호로, 공시 식별과 원문/본문 조인의 기본 키입니다.",
    "records[].title": "공시 제목은 검색/검토/분류에 직접 쓰이고 filing마다 달라지는 사용자-facing 값입니다.",
    "records[].header": "대개 회사명과 종목코드가 들어 있어 공시별 회사 컨텍스트를 빠르게 확인하는 데 필요합니다.",
    "records[].selected_main_doc_no": "현재 선택된 본문 docNo입니다. 실제로 처음 열리는 본문 문서를 특정하므로 다운로드/파싱 기준점으로 보존합니다.",
    "records[].metadata": "현재 샘플은 비어 있어도 원천 검색 row 메타데이터가 들어오면 필터링/감사/조인에 필요합니다.",
    "records[].external_metadata.selects": "mainDoc/attachedDoc option의 docNo, 라벨, 최신 여부, 선택 상태를 원형에 가깝게 담는 canonical 문서 목록입니다.",
    "records[].external_metadata.source_sha256": "원본 HTML을 저장하지 않아도 같은 원본인지 검증할 수 있는 무결성 키입니다.",
    "records[].external_metadata.source_size_bytes": "원본 HTML 누락/절단 여부와 저장량을 빠르게 점검하는 작은 검증 필드입니다.",
}

DISCARD_REASONS = {
    "records[].main_docs": "mainDoc의 docNo, 라벨, selected, latest 정보는 external_metadata.selects에서 50건 모두 0 mismatch로 재구성됩니다. convenience보다 중복 제거를 우선해 제외합니다.",
    "records[].attached_docs": "attachedDoc의 docNo, 라벨, selected 정보는 external_metadata.selects에서 50건 모두 0 mismatch로 재구성됩니다. 첨부 목록도 raw select를 단일 source로 둡니다.",
    "records[].external_metadata.meta": "50건에서 KIND 브라우저 호환/캐시/서비스 설명 메타로 반복됩니다. 공시 식별자나 상태 값이 없어 per-disclosure 저장 이득이 낮습니다.",
    "records[].external_metadata.forms[].attrs": "form name/id/action은 KIND viewer shell 구조입니다. 50건 기준 fetch에 필요한 공시별 값은 attrs가 아니라 input/select 쪽에 있습니다.",
    "records[].external_metadata.forms[].inputs": "form 내부 input을 합치면 external_metadata.inputs와 같은 값입니다. 또한 핵심 값은 acpt_no/title 등 상위 필드와 중복됩니다.",
    "records[].external_metadata.forms[].selects": "form 내부 select를 합치면 external_metadata.selects와 0 mismatch로 동일합니다. top-level selects만 남기는 쪽이 단일 source of truth입니다.",
    "records[].external_metadata.forms[].textareas": "50건에서 비어 있거나 공통 UI shell입니다. 공시별 본문/상태 정보의 근거로 확인되지 않았습니다.",
    "records[].external_metadata.forms[].buttons": "버튼 라벨/onclick은 반복 viewer control입니다. 공시별 식별자나 다운로드 대상 docNo를 새로 제공하지 않습니다.",
    "records[].external_metadata.inputs": "대부분 빈 hidden control, acptNo, tempTitle입니다. acptNo/title은 이미 상위 필드에 있고 나머지는 static viewer state입니다.",
    "records[].external_metadata.links": "PDF/인쇄/닫기 같은 반복 viewer action입니다. 50건에서 공시별 href/docNo source로 쓰일 값이 확인되지 않았습니다.",
    "records[].external_metadata.frames": "toc/doc iframe의 id/name/title 같은 반복 layout shell입니다. 실제 문서 경로는 여기보다 searchContents/setPath 흐름에서 결정됩니다.",
    "records[].external_metadata.resources": "KIND 공통 css/img/static asset 참조입니다. 50건에서 공시별 파일 경로나 본문 식별자를 제공하지 않았습니다.",
    "records[].external_metadata.scripts[].attrs": "script src/version은 공통 viewer 구현 참조입니다. 공시별 상태는 attrs가 아니라 inline 변수/inputs/selects에서 추출됩니다.",
    "records[].external_metadata.scripts[].text": "inline script 전문은 크고 반복 viewer logic이 대부분입니다. 50건에서 단순 변수도 acpt_no/static 값과 중복되어 별도 저장 가치가 낮습니다.",
    "records[].external_metadata.scripts[].variables": "각 script의 variables를 이어 붙이면 flattened script_variables와 50건 모두 동일하고, 그중 유일한 공시별 값 _TRK_PN도 acpt_no와 같습니다.",
    "records[].external_metadata.script_variables": "50건에서 공시별로 변하는 값은 _TRK_PN뿐이며 전부 records[].acpt_no와 같습니다. 나머지는 static/empty/common message라 중복입니다.",
    "records[].external_metadata.text_blocks": "50건에서 대부분 회사명/제목성 텍스트 또는 반복 안내 문구입니다. 회사 컨텍스트는 header/title에 있고, 최종문서 여부는 mainDoc latest/selected 정보로 판단할 수 있어 별도 저장하지 않습니다.",
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
            "records[].metadata": record.get("metadata"),
            "records[].external_metadata.selects": external.get("selects"),
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
        form_inputs = [form.get("inputs") for form in external.get("forms") or [] if form.get("inputs")]
        form_selects = [form.get("selects") for form in external.get("forms") or [] if form.get("selects")]
        form_textareas = [form.get("textareas") for form in external.get("forms") or [] if form.get("textareas")]
        form_buttons = [form.get("buttons") for form in external.get("forms") or [] if form.get("buttons")]
        script_attrs = [script.get("attrs") for script in external.get("scripts") or []]
        script_text = [script.get("text") for script in external.get("scripts") or [] if script.get("text")]
        script_variables = [
            script.get("variables")
            for script in external.get("scripts") or []
            if script.get("variables")
        ]
        values = {
            "records[].main_docs": record.get("main_docs"),
            "records[].attached_docs": record.get("attached_docs"),
            "records[].external_metadata.meta": external.get("meta"),
            "records[].external_metadata.forms[].attrs": form_attrs,
            "records[].external_metadata.forms[].inputs": form_inputs,
            "records[].external_metadata.forms[].selects": form_selects,
            "records[].external_metadata.forms[].textareas": form_textareas,
            "records[].external_metadata.forms[].buttons": form_buttons,
            "records[].external_metadata.inputs": external.get("inputs"),
            "records[].external_metadata.links": external.get("links"),
            "records[].external_metadata.frames": external.get("frames"),
            "records[].external_metadata.resources": external.get("resources"),
            "records[].external_metadata.scripts[].attrs": script_attrs,
            "records[].external_metadata.scripts[].text": script_text,
            "records[].external_metadata.scripts[].variables": script_variables,
            "records[].external_metadata.script_variables": external.get("script_variables"),
            "records[].external_metadata.text_blocks": external.get("text_blocks"),
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
        ("Save Examples", _save_rows(records), [16, 46, 90, 80]),
        ("Discard Examples", _discard_rows(records), [16, 48, 90, 80]),
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
