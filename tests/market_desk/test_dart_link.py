from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from finiq.market_desk.web.app import app
from finiq.market_desk.web.features.disclosure_workflow.dart_link import (
    DartApiError,
    DartListResult,
    OpenDartClient,
    build_dart_links_payload,
    link_kind_disclosures,
    parse_dart_corp_code_payload,
)
from finiq.market_desk.web.routers import workflows as workflows_router


CORP_CODES = [
    {
        "corp_code": "00126380",
        "corp_name": "삼성전자",
        "stock_code": "005930",
        "modify_date": "20250101",
    }
]


class FakeDartClient:
    def __init__(
        self,
        disclosures: list[dict[str, Any]] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.disclosures = disclosures or []
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    def list_disclosures(
        self, *, corp_code: str, begin_date: str, end_date: str
    ) -> DartListResult:
        self.calls.append((corp_code, begin_date, end_date))
        if self.error is not None:
            raise self.error
        return DartListResult(
            records=self.disclosures,
            status="000" if self.disclosures else "013",
            message="정상" if self.disclosures else "조회된 데이터가 없습니다.",
            total_count=len(self.disclosures),
            total_pages=1,
            request_count=1,
            complete=True,
        )


class FakeFullDartClient(FakeDartClient):
    def __init__(self, disclosures: list[dict[str, Any]] | None = None) -> None:
        super().__init__(disclosures)
        self.corp_code_calls = 0

    def fetch_corp_codes(self) -> list[dict[str, str]]:
        self.corp_code_calls += 1
        return [dict(record) for record in CORP_CODES]


def _kind_record(**overrides: Any) -> dict[str, Any]:
    record = {
        "acpt_no": "20250102000001",
        "doc_no": "20250102000011",
        "company_id": "005930",
        "company_name": "삼성전자",
        "disclosed_at": "2025-01-02 09:00:00",
        "title": "전환사채권 발행결정",
        "title_flags": [],
        "submitter": "삼성전자",
    }
    record.update(overrides)
    return record


def _dart_record(**overrides: Any) -> dict[str, Any]:
    record = {
        "corp_code": "00126380",
        "corp_name": "삼성전자",
        "stock_code": "005930",
        "report_nm": "전환사채권 발행결정",
        "rcept_no": "20250102000123",
        "flr_nm": "삼성전자",
        "rcept_dt": "20250102",
        "rm": "",
    }
    record.update(overrides)
    return record


def test_exact_company_date_and_title_match_links_rcept_no() -> None:
    client = FakeDartClient([_dart_record()])

    result = link_kind_disclosures(
        [_kind_record()], corp_code_records=CORP_CODES, client=client
    )

    link = result[0]
    assert link["status"] == "matched"
    assert link["rcept_no"] == "20250102000123"
    assert link["match"]["company_method"] == "stock_code"
    assert link["match"]["title_similarity"] == 1.0
    assert client.calls == [("00126380", "20250101", "20250103")]


def test_no_dart_candidate_in_date_window_is_confirmed_absent() -> None:
    client = FakeDartClient([_dart_record(rcept_dt="20250301")])

    [link] = link_kind_disclosures(
        [_kind_record()], corp_code_records=CORP_CODES, client=client
    )

    assert link["status"] == "confirmed_absent"
    assert link["rcept_no"] is None
    assert link["reason_code"] == "no_dart_candidate_in_date_window"
    assert link["query"]["complete"] is True


def test_candidates_exist_but_title_does_not_match_is_unresolved() -> None:
    client = FakeDartClient([_dart_record(report_nm="사업보고서")])

    [link] = link_kind_disclosures(
        [_kind_record()], corp_code_records=CORP_CODES, client=client
    )

    assert link["status"] == "unresolved"
    assert link["reason_code"] == "no_confident_match"
    assert link["candidate_count"] == 1


def test_invalid_candidate_metadata_is_not_mislabeled_as_absent() -> None:
    client = FakeDartClient([_dart_record(rcept_no="invalid")])

    [link] = link_kind_disclosures(
        [_kind_record()], corp_code_records=CORP_CODES, client=client
    )

    assert link["status"] == "unresolved"
    assert link["reason_code"] == "invalid_dart_candidate_metadata"
    assert link["candidate_count"] == 0


def test_invalid_candidate_date_is_not_mislabeled_as_absent() -> None:
    client = FakeDartClient([_dart_record(rcept_dt="invalid")])

    [link] = link_kind_disclosures(
        [_kind_record()], corp_code_records=CORP_CODES, client=client
    )

    assert link["status"] == "unresolved"
    assert link["reason_code"] == "invalid_dart_candidate_metadata"


def test_original_and_correction_disclosures_are_not_cross_matched() -> None:
    client = FakeDartClient(
        [
            _dart_record(rcept_no="20250102000123"),
            _dart_record(
                rcept_no="20250102000456",
                report_nm="[기재정정]전환사채권 발행결정",
            ),
        ]
    )

    [link] = link_kind_disclosures(
        [_kind_record(title="[기재정정]전환사채권 발행결정")],
        corp_code_records=CORP_CODES,
        client=client,
    )

    assert link["status"] == "matched"
    assert link["rcept_no"] == "20250102000456"
    assert link["match"]["correction_matches"] is True


def test_same_company_and_year_are_queried_once() -> None:
    client = FakeDartClient(
        [
            _dart_record(rcept_no="20250102000123"),
            _dart_record(
                rcept_no="20250203000456",
                rcept_dt="20250203",
                report_nm="유상증자 결정",
            ),
        ]
    )

    links = link_kind_disclosures(
        [
            _kind_record(),
            _kind_record(
                acpt_no="20250203000001",
                doc_no="20250203000011",
                disclosed_at="2025-02-03 10:00:00",
                title="유상증자 결정",
            ),
        ],
        corp_code_records=CORP_CODES,
        client=client,
    )

    assert [link["status"] for link in links] == ["matched", "matched"]
    assert client.calls == [("00126380", "20250101", "20250204")]


def test_year_boundary_is_included_in_date_tolerance() -> None:
    client = FakeDartClient(
        [_dart_record(rcept_no="20241231000123", rcept_dt="20241231")]
    )

    [link] = link_kind_disclosures(
        [_kind_record(disclosed_at="2025-01-01 09:00:00")],
        corp_code_records=CORP_CODES,
        client=client,
    )

    assert link["status"] == "matched"
    assert link["match"]["date_delta_days"] == 1
    assert client.calls == [("00126380", "20241231", "20250102")]


def test_multiple_equally_strong_candidates_are_ambiguous() -> None:
    client = FakeDartClient(
        [
            _dart_record(rcept_no="20250102000123"),
            _dart_record(rcept_no="20250102000456"),
        ]
    )

    [link] = link_kind_disclosures(
        [_kind_record()], corp_code_records=CORP_CODES, client=client
    )

    assert link["status"] == "ambiguous"
    assert link["rcept_no"] is None
    assert link["reason_code"] == "multiple_confident_matches"


def test_unresolved_company_is_not_mislabeled_as_absent() -> None:
    client = FakeDartClient()

    [link] = link_kind_disclosures(
        [_kind_record(company_id="", company_name="알수없는회사")],
        corp_code_records=CORP_CODES,
        client=client,
    )

    assert link["status"] == "unresolved"
    assert link["reason_code"] == "company_not_resolved"
    assert client.calls == []


def test_query_failure_is_distinct_from_confirmed_absent() -> None:
    client = FakeDartClient(error=TimeoutError("temporary timeout"))

    [link] = link_kind_disclosures(
        [_kind_record()], corp_code_records=CORP_CODES, client=client
    )

    assert link["status"] == "lookup_failed"
    assert link["reason_code"] == "dart_query_failed"
    assert link["retryable"] is True
    assert "temporary timeout" not in json.dumps(link, ensure_ascii=False)


def test_incomplete_query_cannot_confirm_absence() -> None:
    class IncompleteClient(FakeDartClient):
        def list_disclosures(
            self, *, corp_code: str, begin_date: str, end_date: str
        ) -> DartListResult:
            self.calls.append((corp_code, begin_date, end_date))
            return DartListResult([], "000", "partial", 10, 10, 1, False)

    [link] = link_kind_disclosures(
        [_kind_record()], corp_code_records=CORP_CODES, client=IncompleteClient()
    )

    assert link["status"] == "lookup_failed"
    assert link["reason_code"] == "incomplete_dart_query"
    assert link["retryable"] is True


def test_query_count_mismatch_cannot_confirm_absence() -> None:
    class CountMismatchClient(FakeDartClient):
        def list_disclosures(
            self, *, corp_code: str, begin_date: str, end_date: str
        ) -> DartListResult:
            self.calls.append((corp_code, begin_date, end_date))
            return DartListResult([], "000", "partial", 1, 1, 1, True)

    [link] = link_kind_disclosures(
        [_kind_record()], corp_code_records=CORP_CODES, client=CountMismatchClient()
    )

    assert link["status"] == "lookup_failed"
    assert link["reason_code"] == "incomplete_dart_query"


def test_build_payload_saves_year_partitions_manifest_and_no_html(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    client = FakeDartClient([_dart_record()])
    now = datetime(2026, 7, 11, tzinfo=timezone.utc)

    result = build_dart_links_payload(
        {
            "data_root": str(data_root),
            "records": [_kind_record()],
            "corp_code_records": CORP_CODES,
        },
        client=client,
        now=now,
    )

    output_directory = data_root / "01-list" / "dart-links"
    assert result["format"] == "finiq_kind_dart_link_build_v1"
    assert (output_directory / "years" / "2025.json").is_file()
    manifest = json.loads(
        (output_directory / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["summary"]["matched"] == 1
    assert manifest["contains_dart_html"] is False
    assert list(output_directory.rglob("*.html")) == []


def test_invalid_kind_date_is_saved_as_undated_unresolved(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"

    result = build_dart_links_payload(
        {
            "data_root": str(data_root),
            "records": [_kind_record(disclosed_at="invalid")],
            "corp_code_records": CORP_CODES,
        },
        client=FakeDartClient(error=AssertionError("must not query")),
    )

    output_directory = data_root / "01-list" / "dart-links"
    undated = json.loads(
        (output_directory / "undated.json").read_text(encoding="utf-8")
    )
    assert result["summary"]["unresolved"] == 1
    assert undated["year"] is None
    assert undated["links"][0]["reason_code"] == "invalid_disclosed_date"
    assert not (output_directory / "years" / "unknown.json").exists()


def test_unresolved_company_does_not_require_api_key(tmp_path: Path) -> None:
    result = build_dart_links_payload(
        {
            "data_root": str(tmp_path / "workspace"),
            "records": [
                _kind_record(company_id="", company_name="DART에 없는 회사")
            ],
            "corp_code_records": CORP_CODES,
        }
    )

    assert result["summary"]["unresolved"] == 1
    assert result["summary"]["lookup_failed"] == 0


def test_unchanged_matched_link_is_reused_without_query(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    first_client = FakeDartClient([_dart_record()])
    payload = {
        "data_root": str(data_root),
        "records": [_kind_record()],
        "corp_code_records": CORP_CODES,
    }
    build_dart_links_payload(payload, client=first_client, now=now)
    second_client = FakeDartClient(error=AssertionError("must not query"))

    result = build_dart_links_payload(payload, client=second_client, now=now)

    assert result["summary"]["reused"] == 1
    assert second_client.calls == []


def test_kind_acpt_no_is_preserved_in_sidecar_and_cache_identity(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "workspace"
    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    spaced_record = _kind_record(acpt_no=" report ")

    build_dart_links_payload(
        {
            "data_root": str(data_root),
            "records": [spaced_record],
            "corp_code_records": CORP_CODES,
        },
        client=FakeDartClient([_dart_record()]),
        now=now,
    )

    partition_path = data_root / "01-list" / "dart-links" / "years" / "2025.json"
    partition = json.loads(partition_path.read_text(encoding="utf-8"))
    assert partition["links"][0]["acpt_no"] == " report "

    client = FakeDartClient([_dart_record()])
    result = build_dart_links_payload(
        {
            "data_root": str(data_root),
            "records": [_kind_record(acpt_no="report")],
            "corp_code_records": CORP_CODES,
        },
        client=client,
        now=now,
    )

    assert result["summary"]["reused"] == 0
    assert len(client.calls) == 1


def test_corrupt_matched_link_is_not_reused(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    payload = {
        "data_root": str(data_root),
        "records": [_kind_record()],
        "corp_code_records": CORP_CODES,
    }
    build_dart_links_payload(payload, client=FakeDartClient([_dart_record()]), now=now)
    partition_path = data_root / "01-list" / "dart-links" / "years" / "2025.json"
    partition = json.loads(partition_path.read_text(encoding="utf-8"))
    partition["links"][0]["rcept_no"] = "broken"
    partition_path.write_text(json.dumps(partition), encoding="utf-8")
    client = FakeDartClient([_dart_record()])

    result = build_dart_links_payload(payload, client=client, now=now)

    assert result["summary"]["reused"] == 0
    assert len(client.calls) == 1


def test_confirmed_absent_cache_expires_and_is_rechecked(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    first_time = datetime(2026, 7, 1, tzinfo=timezone.utc)
    payload = {
        "data_root": str(data_root),
        "records": [_kind_record()],
        "corp_code_records": CORP_CODES,
        "negative_cache_days": 7,
    }
    build_dart_links_payload(payload, client=FakeDartClient(), now=first_time)
    fresh_client = FakeDartClient(error=AssertionError("must use fresh negative cache"))

    fresh = build_dart_links_payload(
        payload, client=fresh_client, now=first_time + timedelta(days=6)
    )

    assert fresh["summary"]["reused"] == 1
    assert fresh_client.calls == []

    stale_client = FakeDartClient(error=TimeoutError("recheck failed"))
    stale = build_dart_links_payload(
        payload, client=stale_client, now=first_time + timedelta(days=8)
    )

    assert stale["summary"]["lookup_failed"] == 1
    assert stale["summary"]["reused"] == 0
    assert len(stale_client.calls) == 1


def test_zero_day_negative_cache_forces_recheck(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    payload = {
        "data_root": str(data_root),
        "records": [_kind_record()],
        "corp_code_records": CORP_CODES,
        "negative_cache_days": 0,
    }
    build_dart_links_payload(payload, client=FakeDartClient(), now=now)
    second_client = FakeDartClient([_dart_record()])

    result = build_dart_links_payload(payload, client=second_client, now=now)

    assert result["summary"]["reused"] == 0
    assert result["summary"]["matched"] == 1
    assert len(second_client.calls) == 1


def test_duplicate_kind_identifiers_are_rejected_before_reuse(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Duplicate KIND acpt_no"):
        build_dart_links_payload(
            {
                "data_root": str(tmp_path / "workspace"),
                "records": [_kind_record(), _kind_record()],
                "corp_code_records": CORP_CODES,
            },
            client=FakeDartClient(),
        )


def test_non_object_kind_record_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"records\[1\]"):
        build_dart_links_payload(
            {
                "data_root": str(tmp_path / "workspace"),
                "records": [_kind_record(), "invalid"],
                "corp_code_records": CORP_CODES,
            },
            client=FakeDartClient(),
        )


def test_dart_output_does_not_overwrite_unowned_year_partition(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "dart-links"
    partition_path = output_directory / "years" / "2025.json"
    partition_path.parent.mkdir(parents=True)
    original = {"format": "unrelated", "records": [1]}
    partition_path.write_text(json.dumps(original), encoding="utf-8")
    client = FakeDartClient(error=AssertionError("must not query"))

    with pytest.raises(ValueError, match="not a FINIQ DART link artifact"):
        build_dart_links_payload(
            {
                "output_directory": str(output_directory),
                "records": [_kind_record()],
                "corp_code_records": CORP_CODES,
            },
            client=client,
        )

    assert json.loads(partition_path.read_text(encoding="utf-8")) == original
    assert client.calls == []


def test_dart_build_preserves_unrelated_year_directory_json(tmp_path: Path) -> None:
    output_directory = tmp_path / "dart-links"
    notes_path = output_directory / "years" / "notes.json"
    notes_path.parent.mkdir(parents=True)
    notes_path.write_text(json.dumps({"notes": [1]}), encoding="utf-8")

    build_dart_links_payload(
        {
            "output_directory": str(output_directory),
            "records": [_kind_record()],
            "corp_code_records": CORP_CODES,
        },
        client=FakeDartClient([_dart_record()]),
    )

    assert json.loads(notes_path.read_text(encoding="utf-8")) == {"notes": [1]}


def test_corp_code_list_is_cached_without_api_key(tmp_path: Path) -> None:
    data_root = tmp_path / "workspace"
    now = datetime(2026, 7, 11, tzinfo=timezone.utc)
    first_client = FakeFullDartClient([_dart_record()])

    build_dart_links_payload(
        {"data_root": str(data_root), "records": [_kind_record()]},
        client=first_client,
        now=now,
    )

    cache_path = data_root / "01-list" / "dart-links" / "cache" / "corp-codes.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert first_client.corp_code_calls == 1
    assert cache["records"] == CORP_CODES
    assert "dart_api_key" not in json.dumps(cache)

    second_client = FakeDartClient(
        [
            _dart_record(
                rcept_no="20250203000456",
                rcept_dt="20250203",
                report_nm="유상증자 결정",
            )
        ]
    )
    result = build_dart_links_payload(
        {
            "data_root": str(data_root),
            "records": [
                _kind_record(
                    acpt_no="20250203000001",
                    doc_no="20250203000011",
                    disclosed_at="2025-02-03 10:00:00",
                    title="유상증자 결정",
                )
            ],
        },
        client=second_client,
        now=now + timedelta(days=1),
    )

    assert result["summary"]["matched"] == 1
    assert len(second_client.calls) == 1


@pytest.mark.parametrize(
    "cached_records",
    [
        [],
        [{"corp_code": "invalid", "corp_name": "삼성전자"}],
        [{"corp_code": "00126380", "corp_name": ""}],
    ],
)
def test_invalid_corp_code_cache_is_refetched(
    tmp_path: Path, cached_records: list[dict[str, str]]
) -> None:
    data_root = tmp_path / "workspace"
    cache_path = data_root / "01-list" / "dart-links" / "cache" / "corp-codes.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(
        json.dumps(
            {
                "format": "finiq_dart_corp_codes_v1",
                "fetched_at": "2026-07-11T00:00:00+00:00",
                "records": cached_records,
            }
        ),
        encoding="utf-8",
    )
    client = FakeFullDartClient([_dart_record()])

    result = build_dart_links_payload(
        {"data_root": str(data_root), "records": [_kind_record()]},
        client=client,
        now=datetime(2026, 7, 12, tzinfo=timezone.utc),
    )

    assert client.corp_code_calls == 1
    assert result["summary"]["matched"] == 1


def test_dart_link_build_api_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_build(payload: dict[str, Any]) -> dict[str, Any]:
        captured.update(payload)
        return {
            "format": "finiq_kind_dart_link_build_v1",
            "contains_dart_html": False,
            "summary": {"matched": 1},
        }

    monkeypatch.setattr(workflows_router, "build_dart_links_payload", fake_build)

    response = TestClient(app).post(
        "/api/disclosures/dart-links/build",
        json={"records": [_kind_record()], "output_directory": "/tmp/dart-links"},
    )

    assert response.status_code == 200
    assert response.json()["contains_dart_html"] is False
    assert captured["records"][0]["acpt_no"] == "20250102000001"


class _FakeResponse:
    def __init__(
        self,
        *,
        payload: dict[str, Any] | None = None,
        content: bytes = b"",
        status_code: int = 200,
    ) -> None:
        self._payload = payload
        self.content = content
        self.status_code = status_code
        self.is_redirect = False
        self.is_permanent_redirect = False

    def json(self) -> dict[str, Any]:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class _FakeSession:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.max_redirects = 30

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def test_open_dart_client_fetches_all_list_pages_without_html() -> None:
    session = _FakeSession(
        [
            _FakeResponse(
                payload={
                    "status": "000",
                    "message": "정상",
                    "page_no": 1,
                    "page_count": 1,
                    "total_count": 2,
                    "total_page": 2,
                    "list": [_dart_record(rcept_no="20250102000123")],
                }
            ),
            _FakeResponse(
                payload={
                    "status": "000",
                    "message": "정상",
                    "page_no": 2,
                    "page_count": 1,
                    "total_count": 2,
                    "total_page": 2,
                    "list": [_dart_record(rcept_no="20250103000456")],
                }
            ),
        ]
    )
    client = OpenDartClient(
        "x" * 40,
        session=session,  # type: ignore[arg-type]
        min_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    result = client.list_disclosures(
        corp_code="00126380", begin_date="20250101", end_date="20251231"
    )

    assert result.complete is True
    assert [record["rcept_no"] for record in result.records] == [
        "20250102000123",
        "20250103000456",
    ]
    assert len(session.calls) == 2
    assert all(call["url"].endswith("/list.json") for call in session.calls)
    assert all(call["allow_redirects"] is False for call in session.calls)
    assert all(call["params"]["last_reprt_at"] == "N" for call in session.calls)
    assert all("crtfc_key" in call["params"] for call in session.calls)


def test_open_dart_no_data_response_is_complete() -> None:
    session = _FakeSession(
        [
            _FakeResponse(
                payload={
                    "status": "013",
                    "message": "조회된 데이터가 없습니다.",
                }
            )
        ]
    )
    client = OpenDartClient(
        "x" * 40,
        session=session,  # type: ignore[arg-type]
        min_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    result = client.list_disclosures(
        corp_code="00126380", begin_date="20250101", end_date="20250103"
    )

    assert result.status == "013"
    assert result.complete is True
    assert result.records == []
    assert result.request_count == 1


def test_open_dart_retries_http_429_with_bounded_attempts() -> None:
    session = _FakeSession(
        [
            _FakeResponse(status_code=429),
            _FakeResponse(payload={"status": "013", "message": "no data"}),
        ]
    )
    sleeps: list[float] = []
    client = OpenDartClient(
        "x" * 40,
        session=session,  # type: ignore[arg-type]
        max_attempts=2,
        min_interval_seconds=0,
        sleep=sleeps.append,
    )

    result = client.list_disclosures(
        corp_code="00126380", begin_date="20250101", end_date="20250103"
    )

    assert result.complete is True
    assert result.request_count == 2
    assert len(session.calls) == 2
    assert sleeps == [1]


def test_open_dart_retries_retryable_api_status_with_bounded_attempts() -> None:
    session = _FakeSession(
        [
            _FakeResponse(payload={"status": "020", "message": "limit"}),
            _FakeResponse(payload={"status": "013", "message": "no data"}),
        ]
    )
    sleeps: list[float] = []
    client = OpenDartClient(
        "x" * 40,
        session=session,  # type: ignore[arg-type]
        max_attempts=2,
        min_interval_seconds=0,
        sleep=sleeps.append,
    )

    result = client.list_disclosures(
        corp_code="00126380", begin_date="20250101", end_date="20250103"
    )

    assert result.complete is True
    assert result.request_count == 2
    assert len(session.calls) == 2
    assert sleeps == [1]


def test_open_dart_rejects_pagination_metadata_drift() -> None:
    session = _FakeSession(
        [
            _FakeResponse(
                payload={
                    "status": "000",
                    "page_no": 1,
                    "total_count": 2,
                    "total_page": 2,
                    "list": [_dart_record(rcept_no="20250102000123")],
                }
            ),
            _FakeResponse(
                payload={
                    "status": "000",
                    "page_no": 2,
                    "total_count": 2,
                    "total_page": 1,
                    "list": [_dart_record(rcept_no="20250103000456")],
                }
            ),
        ]
    )
    client = OpenDartClient(
        "x" * 40,
        session=session,  # type: ignore[arg-type]
        min_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    with pytest.raises(DartApiError) as error:
        client.list_disclosures(
            corp_code="00126380", begin_date="20250101", end_date="20250103"
        )

    assert error.value.code == "pagination_changed"
    assert error.value.retryable is True


def test_open_dart_rejects_duplicate_list_records() -> None:
    duplicate = _dart_record(rcept_no="20250102000123")
    session = _FakeSession(
        [
            _FakeResponse(
                payload={
                    "status": "000",
                    "page_no": 1,
                    "total_count": 2,
                    "total_page": 2,
                    "list": [duplicate],
                }
            ),
            _FakeResponse(
                payload={
                    "status": "000",
                    "page_no": 2,
                    "total_count": 2,
                    "total_page": 2,
                    "list": [duplicate],
                }
            ),
        ]
    )
    client = OpenDartClient(
        "x" * 40,
        session=session,  # type: ignore[arg-type]
        min_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    with pytest.raises(DartApiError) as error:
        client.list_disclosures(
            corp_code="00126380", begin_date="20250101", end_date="20250103"
        )

    assert error.value.code == "duplicate_list_record"
    assert error.value.retryable is True


def test_open_dart_cancel_check_stops_between_pages() -> None:
    session = _FakeSession(
        [
            _FakeResponse(
                payload={
                    "status": "000",
                    "page_no": 1,
                    "total_count": 2,
                    "total_page": 2,
                    "list": [_dart_record(rcept_no="20250102000123")],
                }
            )
        ]
    )
    checks = iter([False, True])
    client = OpenDartClient(
        "x" * 40,
        session=session,  # type: ignore[arg-type]
        min_interval_seconds=0,
        sleep=lambda _seconds: None,
        cancel_check=lambda: next(checks),
    )

    with pytest.raises(RuntimeError, match="Job cancelled"):
        client.list_disclosures(
            corp_code="00126380", begin_date="20250101", end_date="20250103"
        )

    assert len(session.calls) == 1


def test_parse_dart_corp_code_zip_payload() -> None:
    xml_payload = b"""<?xml version='1.0' encoding='UTF-8'?>
<result><list><corp_code>00126380</corp_code><corp_name>Samsung</corp_name>
<stock_code>005930</stock_code><modify_date>20250101</modify_date></list></result>"""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("CORPCODE.xml", xml_payload)

    records = parse_dart_corp_code_payload(buffer.getvalue())

    assert records == [
        {
            "corp_code": "00126380",
            "corp_name": "Samsung",
            "stock_code": "005930",
            "modify_date": "20250101",
        }
    ]
