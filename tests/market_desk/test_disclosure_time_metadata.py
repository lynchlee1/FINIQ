from __future__ import annotations

import json
from pathlib import Path

import pytest

from finiq.market_desk.web.features.disclosure_workflow.layout import (
    apply_workspace_defaults,
    prepare_disclosure_workspace_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_common import (
    PARSER_REGISTRY,
    parse_disclosure_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_preview import (
    build_parse_preview_payload,
)


def _fake_parser(_html: bytes, *, file_path: Path) -> dict[str, object]:
    return {
        "acpt_no": file_path.stem,
        "mode": "bond_issuance",
        "title": "",
        "disclosed_at": "1900-01-01 00:00",
        "raw_tables": [],
    }


def _write_filtered(path: Path, *, disclosed_at: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "format": "kind_disclosure_filter_v1",
                "disclosures": [
                    {
                        "acpt_no": "20250102000001",
                        "company_name": "테스트회사",
                        "market": "코스닥",
                        "disclosed_at": disclosed_at,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_source_html(input_directory: Path, acpt_no: str) -> None:
    source_path = input_directory / acpt_no[:4] / f"{acpt_no}.html"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("<html></html>", encoding="utf-8")


def test_final_parse_record_preserves_kind_disclosed_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_directory = tmp_path / "sections"
    input_directory.mkdir()
    _write_source_html(input_directory, "20250102000001")
    _write_filtered(tmp_path / "filtered.json", disclosed_at="2025-01-02 09:37")
    monkeypatch.setitem(PARSER_REGISTRY, "bond_issuance", _fake_parser)

    result = parse_disclosure_html_payload(
        {
            "input_directory": str(input_directory),
            "output_directory": str(tmp_path / "converted"),
            "mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "skip_errors": False,
            "filtered_metadata_path": str(tmp_path / "filtered.json"),
        }
    )

    assert result["records"][0]["disclosed_at"] == "2025-01-02 09:37"
    stored = json.loads(
        (tmp_path / "converted" / "parsed-bond_issuance.json").read_text(
            encoding="utf-8"
        )
    )
    assert stored["records"][0]["disclosed_at"] == "2025-01-02 09:37"


def test_workspace_parse_reads_kind_time_from_stage_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "workspace"
    prepare_disclosure_workspace_payload(
        {"data_root": str(data_root), "modes": ["bond_issuance"]}
    )
    source_path = (
        data_root / "06-sections" / "bond_issuance" / "2025" / "20250102000001.html"
    )
    source_path.parent.mkdir(parents=True)
    source_path.write_text("<html></html>", encoding="utf-8")
    _write_filtered(
        data_root / "03-filter" / "bond_issuance" / "filtered.json",
        disclosed_at="2025-01-02 18:42",
    )
    compressed_path = (
        data_root
        / "04-external-html-compress"
        / "bond_issuance"
        / "compressed-external-html.json"
    )
    compressed_path.parent.mkdir(parents=True, exist_ok=True)
    compressed_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_external_html_docs_v1",
                "summary": {"found_files": 0, "compressed_files": 0},
                "records": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(PARSER_REGISTRY, "bond_issuance", _fake_parser)
    payload = apply_workspace_defaults(
        "parse",
        {
            "data_root": str(data_root),
            "mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "skip_errors": False,
        },
    )

    result = parse_disclosure_html_payload(payload)

    assert payload["filtered_metadata_path"] == str(
        data_root / "03-filter" / "bond_issuance" / "filtered.json"
    )
    assert payload["compressed_metadata_path"] == str(
        data_root
        / "04-external-html-compress"
        / "bond_issuance"
        / "compressed-external-html.json"
    )
    assert result["records"][0]["disclosed_at"] == "2025-01-02 18:42"
    preview = build_parse_preview_payload(payload)
    assert preview["records"][0]["parsed_result"]["disclosed_at"] == (
        "2025-01-02 18:42"
    )


def test_explicit_missing_kind_metadata_is_not_silently_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_directory = tmp_path / "sections"
    input_directory.mkdir()
    _write_source_html(input_directory, "20250102000001")
    monkeypatch.setitem(PARSER_REGISTRY, "bond_issuance", _fake_parser)

    with pytest.raises(ValueError, match="filtered_metadata_path does not exist"):
        parse_disclosure_html_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(tmp_path / "converted"),
                "mode": "bond_issuance",
                "parser_method": "bond_issuance",
                "skip_errors": False,
                "filtered_metadata_path": str(tmp_path / "missing-filtered.json"),
            }
        )


def test_explicit_kind_metadata_must_cover_every_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_directory = tmp_path / "sections"
    input_directory.mkdir()
    _write_source_html(input_directory, "20250102000002")
    _write_filtered(tmp_path / "filtered.json", disclosed_at="2025-01-02 09:37")
    monkeypatch.setitem(PARSER_REGISTRY, "bond_issuance", _fake_parser)

    with pytest.raises(ValueError, match="missing KIND disclosed_at metadata"):
        parse_disclosure_html_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(tmp_path / "converted"),
                "mode": "bond_issuance",
                "parser_method": "bond_issuance",
                "skip_errors": False,
                "filtered_metadata_path": str(tmp_path / "filtered.json"),
            }
        )


def test_explicit_kind_metadata_rejects_invalid_disclosed_at(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_directory = tmp_path / "sections"
    input_directory.mkdir()
    _write_source_html(input_directory, "20250102000001")
    _write_filtered(tmp_path / "filtered.json", disclosed_at="2025-13-40 99:99")
    monkeypatch.setitem(PARSER_REGISTRY, "bond_issuance", _fake_parser)

    with pytest.raises(ValueError, match="invalid KIND disclosed_at metadata"):
        parse_disclosure_html_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(tmp_path / "converted"),
                "mode": "bond_issuance",
                "parser_method": "bond_issuance",
                "skip_errors": False,
                "filtered_metadata_path": str(tmp_path / "filtered.json"),
            }
        )


def test_duplicate_kind_metadata_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_directory = tmp_path / "sections"
    input_directory.mkdir()
    _write_source_html(input_directory, "20250102000001")
    filtered_path = tmp_path / "filtered.json"
    filtered_path.write_text(
        json.dumps(
            {
                "format": "kind_disclosure_filter_v1",
                "disclosures": [
                    {
                        "acpt_no": "20250102000001",
                        "disclosed_at": "2025-01-02 09:37",
                    },
                    {
                        "acpt_no": "20250102000001",
                        "disclosed_at": "2025-01-02 10:41",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setitem(PARSER_REGISTRY, "bond_issuance", _fake_parser)

    with pytest.raises(ValueError, match="duplicate KIND metadata acpt_no"):
        parse_disclosure_html_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(tmp_path / "converted"),
                "mode": "bond_issuance",
                "parser_method": "bond_issuance",
                "skip_errors": False,
                "filtered_metadata_path": str(filtered_path),
            }
        )
