from __future__ import annotations

import json
from pathlib import Path

import pytest

from finiq.market_desk.web.features.disclosures.html_cleanup import (
    check_disclosure_html_output_directory_payload,
)
from finiq.market_desk.web.features.disclosures.html_content_download import (
    download_disclosure_content_htmls,
    download_disclosure_html_contents_payload,
)
from finiq.market_desk.web.features.disclosures.html_download import (
    download_disclosure_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_external_compress import (
    compress_disclosure_external_html_payload,
)


def _valid_html(label: str = "valid") -> str:
    return f"<html><body>{label * 30}</body></html>"


def test_external_html_resume_redownloads_invalid_existing_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_directory = tmp_path / "external"
    (output_directory / "2025").mkdir(parents=True)
    target = output_directory / "2025" / "20250101000001.html"
    target.write_text("broken", encoding="utf-8")

    inspection = check_disclosure_html_output_directory_payload(
        {
            "output_directory": str(output_directory),
            "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
        }
    )
    assert inspection["existing_target_html_count"] == 0
    assert inspection["missing_target_html_count"] == 1
    assert inspection["invalid_target_html_count"] == 1
    assert inspection["auxiliary_file_count"] == 0

    def fake_download(**kwargs: object) -> list[Path]:
        assert kwargs["acpt_numbers"] == ["20250101000001"]
        target.write_text(_valid_html(), encoding="utf-8")
        return [target]

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.html_download.download_disclosure_viewer_htmls",
        fake_download,
    )

    result = download_disclosure_html_payload(
        {
            "output_directory": str(output_directory),
            "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
            "skip_existing": True,
        }
    )

    assert result["saved_count"] == 1
    assert target.read_text("utf-8") == _valid_html()


def test_content_html_download_rejects_invalid_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.html_content_download._fetch_content_html",
        lambda *args, **kwargs: b"invalid",
    )

    with pytest.raises(ValueError, match="invalid HTML"):
        download_disclosure_content_htmls(
            output_directory=tmp_path,
            request_headers={},
            targets=[{"acpt_no": "20250101000001", "doc_no": "1"}],
            max_requests_per_minute=100,
        )

    assert not (tmp_path / "20250101000001.html").exists()


def test_download_payload_reports_parent_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.html_download.download_disclosure_viewer_htmls",
        lambda **kwargs: [],
    )

    result = download_disclosure_html_payload(
        {
            "output_directory": str(tmp_path / "external"),
            "json": {"disclosures": [{"acpt_no": "20250101000001"}]},
        },
        cancel_check=lambda: True,
    )

    assert result["cancelled"] is True
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["disclosures"] == []


def test_content_download_cancellation_manifest_lists_only_saved_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    external_directory = tmp_path / "external"
    (external_directory / "2025").mkdir(parents=True)
    (external_directory / "2025" / "20250101000001.html").write_text(
        "<html><body><select id='mainDoc'><option value='1|Y' selected>본문</option></select></body></html>",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.html_content_download.download_disclosure_content_htmls",
        lambda **kwargs: [],
    )

    result = download_disclosure_html_contents_payload(
        {
            "output_directory": str(tmp_path / "content"),
            "source_directory": str(external_directory),
        },
        cancel_check=lambda: True,
    )

    assert result["cancelled"] is True
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["disclosures"] == []


def test_external_compression_rejects_receipt_number_mismatching_filename(
    tmp_path: Path,
) -> None:
    input_directory = tmp_path / "external"
    (input_directory / "2025").mkdir(parents=True)
    (input_directory / "2025" / "20250101000001.html").write_text(
        """
        <html><body>
          <input type="hidden" name="acptNo" value="20250101000002" />
          <select id="mainDoc">
            <option value="20250101000999|Y" selected="selected">본문</option>
          </select>
        </body></html>
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="membership does not match"):
        compress_disclosure_external_html_payload(
            {
                "input_directory": str(input_directory),
                "output_directory": str(tmp_path / "compressed"),
            }
        )

    assert not (tmp_path / "compressed" / "compressed-external-html.json").exists()
