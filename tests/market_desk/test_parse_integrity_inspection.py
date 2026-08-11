from pathlib import Path

import pytest

from finiq.market_desk.web.features.disclosures import html_parse_common


def _parse_result() -> dict[str, object]:
    return {
        "format": "finiq_disclosure_html_parse_v1",
        "mode": "bond_issuance",
        "cancelled": False,
        "filter_settings": {"filter_blocks": [], "record_filters": []},
        "warning_report_counts": {},
        "summary": {"found_files": 1, "parsed_files": 1, "failed_files": 0},
        "families": {},
        "records": [{"acpt_no": "20260101000001"}],
        "errors": [],
        "warnings": [],
    }


def test_parse_inspection_recomputes_and_confirms_saved_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = _parse_result()
    monkeypatch.setattr(html_parse_common, "_load_parse_payload", lambda _path: saved)
    monkeypatch.setattr(
        html_parse_common,
        "parse_disclosure_html_payload",
        lambda _body: saved,
    )

    result = html_parse_common.inspect_disclosure_html_parse_payload(
        {
            "mode": "bond_issuance",
            "input_directory": str(tmp_path / "06-sections"),
            "output_directory": str(tmp_path / "07-converted"),
        }
    )

    assert result["confirmed"] is True
    assert result["summary"] == saved["summary"]
    assert result["reason"] == "현재 설정으로 다시 변환한 내용이 저장된 결과와 모두 일치합니다."


def test_parse_inspection_rejects_recomputed_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved = _parse_result()
    rebuilt = {**saved, "records": []}
    monkeypatch.setattr(html_parse_common, "_load_parse_payload", lambda _path: saved)
    monkeypatch.setattr(
        html_parse_common,
        "parse_disclosure_html_payload",
        lambda _body: rebuilt,
    )

    result = html_parse_common.inspect_disclosure_html_parse_payload(
        {
            "mode": "bond_issuance",
            "input_directory": str(tmp_path / "06-sections"),
            "output_directory": str(tmp_path / "07-converted"),
        }
    )

    assert result["confirmed"] is False
    assert result["reason"] == "현재 설정과 입력 HTML로 다시 계산한 결과가 저장된 변환 결과와 다릅니다."
