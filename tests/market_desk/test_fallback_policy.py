from __future__ import annotations

from pathlib import Path

import pytest

from finiq.data.ontology_query import OntologyGraphQueryService
from finiq.data_scraper.storage.result_files import result_page_number
from finiq.market_desk.web.features.disclosures import external_compact
from finiq.market_desk.web.features.disclosures.external_compact import (
    _compress_external_html_file,
)
from finiq.market_desk.web.features.disclosures.html_common import (
    _year_from_disclosure,
)
from finiq.market_desk.web.features.downloads.kind_common import (
    DownloadInputMetadataError,
    _build_search_filters,
    _filters_payloads_match,
    _normalize_disclosure_type_groups,
    _snapshot_filters_payload,
)
from finiq.data_scraper.workflow import KIND_WORKFLOW_INPUT_FORMAT
from finiq.market_desk.web.features.market_data import service_payloads
from finiq.market_desk.web.features.market_data.service_common import (
    _result_page_number as market_data_result_page_number,
)
from finiq.market_desk.web.features.market_data.service_integrated import (
    run_integrated_merge_payload,
)


def test_download_search_rejects_unknown_conditions() -> None:
    with pytest.raises(ValueError, match="unsupported market_label"):
        _build_search_filters({"market_label": "알 수 없는 시장"})
    with pytest.raises(ValueError, match="unsupported securities_label"):
        _build_search_filters({"securities_label": "알 수 없는 증권"})
    with pytest.raises(ValueError, match="unsupported disclosure_type_groups"):
        _normalize_disclosure_type_groups(
            {"disclosure_type_groups": {"01": ["not-a-kind-code"]}}
        )


def test_known_saved_filters_are_compared_without_unknown_state() -> None:
    assert _filters_payloads_match({}, {}) is True


def test_unknown_saved_filters_stop_existing_result_inspection() -> None:
    snapshot = {
        "format": KIND_WORKFLOW_INPUT_FORMAT,
        "request_headers": {"User-Agent": "pytest"},
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "page_size": 100,
        "search_filters": {"marketType": "unknown"},
        "disclosure_type_groups": {},
        "last_report_only": False,
        "include_previous_disclosures": None,
        "wait_seconds_between_requests": 0,
        "timeout": 20,
    }

    with pytest.raises(DownloadInputMetadataError, match="cannot be normalized"):
        _snapshot_filters_payload(snapshot)


def test_disclosure_year_requires_disclosed_at_without_receipt_fallback() -> None:
    with pytest.raises(ValueError, match="disclosed_at is required"):
        _year_from_disclosure("20250101000001", {})
    assert _year_from_disclosure(
        "20250101000001", {"disclosed_at": "2024-12-31 09:00"}
    ) == "2024"


def test_integrated_merge_rejects_legacy_input_directory() -> None:
    with pytest.raises(ValueError, match="input_directories must be a non-empty array"):
        run_integrated_merge_payload({"input_directory": "legacy", "output_directory": "unused"})


def test_result_page_number_rejects_noncanonical_filename() -> None:
    with pytest.raises(ValueError, match="Invalid KIND result page filename"):
        result_page_number("001_post_page_unknown.body")
    with pytest.raises(ValueError, match="Invalid KIND result page filename"):
        market_data_result_page_number("001_post_page_unknown.body")


def test_external_compression_requires_selected_main_document(tmp_path: Path) -> None:
    html_path = tmp_path / "20250101000001.html"
    html_path.write_text(
        """
        <html><body>
          <input name="acptNo" value="20250101000001" />
          <select id="mainDoc"><option value="1|Y">본문</option></select>
          <select id="attachedDoc"><option value="2">첨부</option></select>
        </body></html>
        """,
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="selected mainDoc is required"):
        _compress_external_html_file((0, "2025", html_path))


def test_external_compaction_uses_shared_viewer_reader_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_viewer_html(
        _markup: bytes, *, require_complete_metadata: bool = False
    ) -> dict[str, object]:
        nonlocal calls
        calls += 1
        assert require_complete_metadata is True
        return {
            "acpt_no": "20250101000001",
            "selected_main_doc_no": "20250101000999",
            "main_docs": [],
            "attached_docs": [],
        }

    monkeypatch.setattr(external_compact, "viewer_html", fake_viewer_html)

    parsed = external_compact._compact_external_viewer_html(b"")

    assert calls == 1
    assert parsed["documents"] == []


def test_company_index_preserves_explicit_zero_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        service_payloads,
        "load_company_classification_index_file",
        lambda _path: {
            "summary": {"companies": 0, "disclosures": 0},
            "companies": [
                {
                    "company_id": "005930",
                    "company_name": "테스트전자",
                    "market": "코스피",
                    "disclosure_count": 1,
                }
            ],
        },
    )

    payload = service_payloads.load_company_index_payload("unused.sqlite")

    assert payload["summary"]["companies"] == 0


def test_ontology_query_rejects_dangling_edges(tmp_path: Path) -> None:
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        '{"nodes":[{"id":"company-1","type":"Company","properties":{}}],'
        '"edges":[{"id":"edge-1","source":"company-1","target":"missing"}]}',
        encoding="utf-8",
    )
    service = OntologyGraphQueryService(graph_json_path=graph_path)

    with pytest.raises(ValueError, match="edges reference missing nodes: edge-1"):
        service.load_index(force=True)
