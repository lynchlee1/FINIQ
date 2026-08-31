from __future__ import annotations

import json

import pandas as pd
import pytest

from finiq.config import load_settings
from finiq.market_desk.analytics.chart import aggregate_price_dataframe
from finiq.market_desk.analytics.ontology_graph import _resolve_frequency
from finiq.market_desk.web.features.disclosures.external_compact import (
    _external_html_compress_workers,
)
from finiq.market_desk.web.features.disclosures.external_html_download import (
    download_disclosure_external_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_common import (
    _source_json_fingerprint,
)
from finiq.market_desk.web.features.disclosures.html_parse_common import (
    _parse_filter_blocks,
    _parse_parallel_workers,
    _parse_skip_errors,
    _parser_accepts_title,
    parse_disclosure_html_payload,
)
from finiq.market_desk.web.features.disclosures.html_parse_preview import (
    _filter_candidate_workers,
)
from finiq.market_desk.web.features.disclosures.table_export import (
    _resolve_shard_workers,
)
from finiq.market_desk.web.features.market_data.service_common import (
    _resolve_display_frequency,
)
from finiq.market_desk.web.features.market_data.service_payloads import (
    filter_disclosures_payload,
)
from finiq.market_desk.web.features.market_data.service_records import (
    _resolve_filter_workers,
)


def _empty_filter_manifest(tmp_path):
    manifest_path = tmp_path / "02-table" / "sqlite_manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_table_manifest_v1",
                "table_name": "disclosures",
                "shards": [],
                "summary": {"disclosures": 0},
            }
        ),
        encoding="utf-8",
    )
    return manifest_path


@pytest.mark.parametrize(
    ("resolver", "args", "message"),
    [
        (_parse_parallel_workers, ("many", 2), "parallel_workers must be an integer"),
        (_filter_candidate_workers, ("many", 2), "parallel_workers must be an integer"),
        (
            _external_html_compress_workers,
            ({"parallel_workers": "many"}, 2),
            "parallel_workers must be an integer",
        ),
        (_resolve_filter_workers, ("many", 2), "filter_workers must be an integer"),
        (_resolve_shard_workers, ("many", 2), "table_workers must be an integer"),
    ],
)
def test_worker_resolvers_reject_non_numeric_values(resolver, args, message) -> None:
    with pytest.raises(ValueError, match=message):
        resolver(*args)


@pytest.mark.parametrize(
    ("resolver", "args", "message"),
    [
        (_parse_parallel_workers, (0, 2), "parallel_workers must be >= 1"),
        (_filter_candidate_workers, (0, 2), "parallel_workers must be >= 1"),
        (
            _external_html_compress_workers,
            ({"parallel_workers": 0}, 2),
            "parallel_workers must be >= 1",
        ),
        (_resolve_filter_workers, (0, 2), "filter_workers must be >= 1"),
        (_resolve_shard_workers, (0, 2), "table_workers must be >= 1"),
    ],
)
def test_worker_resolvers_reject_non_positive_values(resolver, args, message) -> None:
    with pytest.raises(ValueError, match=message):
        resolver(*args)


def test_missing_worker_values_use_cpu_and_task_limits(monkeypatch) -> None:
    import finiq.concurrency as concurrency

    monkeypatch.setattr(concurrency.os, "cpu_count", lambda: 12)

    assert _parse_parallel_workers("", 2) == 2
    assert _filter_candidate_workers("", 2) == 2
    assert _external_html_compress_workers({"parallel_workers": ""}, 2) == 2
    assert _resolve_filter_workers("", 2) == 2
    assert _resolve_shard_workers("", 2) == 2


def test_external_html_compress_workers_rejects_legacy_alias() -> None:
    with pytest.raises(ValueError, match="workers is not supported"):
        _external_html_compress_workers({"workers": 2}, 2)


@pytest.mark.parametrize(
    ("value", "message"),
    [("many", "max_workers must be an integer"), (0, "max_workers must be >= 1")],
)
def test_html_download_rejects_invalid_worker_values(tmp_path, value, message) -> None:
    filtered_path = (
        tmp_path
        / "workspace"
        / "03-filter"
        / "bond_issuance"
        / "filtered.json"
    )
    filtered_path.parent.mkdir(parents=True)
    filtered = {
        "format": "kind_disclosure_filter_v1",
        "disclosures": [
            {
                "acpt_no": "20250101000001",
                "disclosed_at": "2025-01-01",
            }
        ],
    }
    filtered_path.write_text(
        json.dumps(filtered),
        encoding="utf-8",
    )
    filtered_path.with_name("filter.json").write_text(
        json.dumps(
            {
                "format": "finiq_disclosure_filter_workflow",
                "mode": "bond_issuance",
                "parent_mode": None,
                "status": "completed",
                "result_file": "filtered.json",
                "result_fingerprint": _source_json_fingerprint(filtered),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=message):
        download_disclosure_external_html_payload(
            {
                "data_root": str(tmp_path / "workspace"),
                "mode": "bond_issuance",
                "output_directory": str(tmp_path / "html"),
                "max_workers": value,
            }
        )


@pytest.mark.parametrize("field", ["json", "payload", "source_json_path"])
def test_html_download_rejects_alternate_source_fields(tmp_path, field) -> None:
    with pytest.raises(ValueError, match=rf"{field} is not supported"):
        download_disclosure_external_html_payload(
            {
                "data_root": str(tmp_path / "workspace"),
                "mode": "bond_issuance",
                "output_directory": str(tmp_path / "html"),
                field: {},
            }
        )


def test_filter_blocks_must_be_a_list(tmp_path) -> None:
    with pytest.raises(ValueError, match="filter_blocks must be a list"):
        _parse_filter_blocks({})

    with pytest.raises(ValueError, match="filter_blocks must be a list"):
        filter_disclosures_payload(
            {
                "data_root": str(_empty_filter_manifest(tmp_path).parent.parent),
                "filter_blocks": {},
            }
        )


def test_title_match_mode_must_be_supported(tmp_path) -> None:
    with pytest.raises(ValueError, match="title_match_mode must be one of"):
        filter_disclosures_payload(
            {
                "data_root": str(_empty_filter_manifest(tmp_path).parent.parent),
                "title_match_mode": "xor",
            }
        )


def test_skip_errors_must_be_explicit_boolean(tmp_path) -> None:
    with pytest.raises(ValueError, match="skip_errors is required"):
        parse_disclosure_html_payload(
            {
                "input_directory": str(tmp_path),
                "output_directory": str(tmp_path / "output"),
                "mode": "security_transaction",
                "parser_method": "security_transaction",
            }
        )
    with pytest.raises(ValueError, match="skip_errors must be a boolean"):
        _parse_skip_errors({"skip_errors": "false"})


def test_parser_signature_inspection_failure_is_not_hidden() -> None:
    class UninspectableParser:
        __signature__ = "invalid"

        def __call__(self, *_args, **_kwargs):
            return {}

    with pytest.raises((TypeError, ValueError)):
        _parser_accepts_title(UninspectableParser())


@pytest.mark.parametrize("value", ["분기봉", "", "daily"])
def test_display_frequency_rejects_unknown_values(value) -> None:
    with pytest.raises(ValueError, match="Unsupported display frequency"):
        _resolve_display_frequency(value, 100)
    with pytest.raises(ValueError, match="Unsupported display frequency"):
        _resolve_frequency(value, 100)


@pytest.mark.parametrize(
    ("label", "expected"), [("3일봉", "3day"), ("7일봉", "7day")]
)
def test_ontology_frequency_supports_every_chart_option(label, expected) -> None:
    assert _resolve_frequency(label, 100) == expected


@pytest.mark.parametrize(
    ("frequency", "expected_rows"), [("3day", 3), ("7day", 1)]
)
def test_price_aggregation_supports_three_and_seven_day_candles(
    frequency, expected_rows
) -> None:
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=7),
            "open": range(7),
            "high": range(1, 8),
            "low": range(7),
            "close": range(1, 8),
            "volume": [1] * 7,
            "vwap": range(1, 8),
        }
    )
    assert len(aggregate_price_dataframe(frame, frequency=frequency)) == expected_rows


@pytest.mark.parametrize("payload", ["{broken", "[]"])
def test_load_settings_rejects_invalid_files(tmp_path, payload) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError):
        load_settings(settings_path)


def test_load_settings_allows_a_missing_file(tmp_path) -> None:
    assert load_settings(tmp_path / "missing.json") == {}


def test_load_settings_does_not_hide_read_failures(tmp_path) -> None:
    with pytest.raises(OSError):
        load_settings(tmp_path)
