from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from finiq.market_desk.web.features.disclosures import html_content_download
from finiq.market_desk.web.features.disclosure_workflow import automation
from finiq.market_desk.web.features.disclosure_workflow.automation import (
    AUTOMATION_CHECKPOINT_FORMAT,
    AUTOMATION_EXTERNAL_FORMAT,
    AUTOMATION_INTERNAL_FORMAT,
    AUTOMATION_SECTIONS_FORMAT,
    _checkpoint_path,
    _load_valid_checkpoint,
    _owned_window_matches,
    _run_stage,
    _stage_config_hash,
    _stage_output_fingerprint,
    _stage_output_paths,
    _window_body_hash,
    _window_ranges,
    build_automation_plan_payload,
    normalize_automation_profile,
)
from finiq.market_desk.web.app import app


def _profile(root: Path, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "테스트 자동화",
        "data_root": str(root),
        "steps": {
            "s1_download": True,
            "s2_table": True,
            "s3_filter": True,
            "s4_external_html": True,
            "s5_content_html": True,
            "s6_sections": True,
            "s7_parse": True,
        },
        "execution_mask": [1, 2, 3, 4, 5, 6, 7],
        "decisions": {
            "s1_search": {
                "start_date": "2026-01-01",
                "end_date": "2026-07-12",
                "market_label": "전체",
                "securities_label": "전체",
                "last_report_only": False,
            },
            "s3_selection": {"filter_blocks": []},
            "s6_sections": {
                "unmatched_policy": "needs_review",
                "section_save_rules": {},
            },
        },
        "execution": {
            "parser_mode": "bond_issuance",
            "page_size": 100,
            "local_workers": 4,
            "timeout": 20,
        },
    }
    payload.update(overrides)
    return payload


def test_normalize_automation_profile_fixes_safe_kind_execution_settings(
    tmp_path: Path,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))

    assert profile["data_root"] == str(tmp_path.resolve())
    assert profile["execution"]["max_requests_per_minute"] == 45
    assert profile["execution"]["mutable_lookback_days"] == 7
    assert profile["execution"]["split_by_year"] is True
    assert profile["decisions"]["s6_sections"]["unmatched_policy"] == "needs_review"


def test_normalize_automation_profile_rejects_non_incremental_last_report_only(
    tmp_path: Path,
) -> None:
    payload = _profile(tmp_path)
    payload["decisions"]["s1_search"]["last_report_only"] = True  # type: ignore[index]

    with pytest.raises(ValueError, match="최종보고서만"):
        normalize_automation_profile(payload)


def test_window_ranges_use_sealed_months_and_seven_mutable_days() -> None:
    ranges = _window_ranges(date(2026, 5, 20), date(2026, 7, 12))

    assert ranges[:3] == [
        (date(2026, 5, 20), date(2026, 5, 31), False),
        (date(2026, 6, 1), date(2026, 6, 30), False),
        (date(2026, 7, 1), date(2026, 7, 5), False),
    ]
    assert ranges[3] == (date(2026, 7, 6), date(2026, 7, 6), True)
    assert ranges[-1] == (date(2026, 7, 12), date(2026, 7, 12), True)
    assert sum(1 for _start, _end, mutable in ranges if mutable) == 7


def test_plan_propagates_stage_one_sync_to_downstream_processing(
    tmp_path: Path,
) -> None:
    plan = build_automation_plan_payload({**_profile(tmp_path), "trigger": "sync"})

    assert plan["execution_allowed"] is True
    assert [stage["plan_action"] for stage in plan["stages"]] == [
        "process",
        "process",
        "process",
        "process",
        "process",
        "process",
        "process",
    ]
    assert plan["kind_limit"] == {"max_requests_per_minute": 45, "max_in_flight": 1}


def test_resume_reuses_valid_stage_checkpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _profile(tmp_path)
    profile = normalize_automation_profile(raw)
    for stage in range(1, 8):
        for output_path in _stage_output_paths(profile, stage):
            if output_path.suffix == ".json":
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text("{}", encoding="utf-8")
            else:
                output_path.mkdir(parents=True, exist_ok=True)
    owner_files = {
        4: ("automation-external.json", AUTOMATION_EXTERNAL_FORMAT),
        5: ("automation-internal.json", AUTOMATION_INTERNAL_FORMAT),
        6: ("automation-sections.json", AUTOMATION_SECTIONS_FORMAT),
    }
    for stage, (filename, owner_format) in owner_files.items():
        output_directory = next(
            path
            for path in _stage_output_paths(profile, stage)
            if path.is_dir()
        )
        (output_directory / filename).write_text(
            json.dumps({"format": owner_format}), encoding="utf-8"
        )
    for stage in range(1, 8):
        checkpoint_path = _checkpoint_path(profile, stage)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            json.dumps(
                {
                    "format": AUTOMATION_CHECKPOINT_FORMAT,
                    "stage": stage,
                    "status": "succeeded",
                    "config_hash": _stage_config_hash(profile, stage),
                    "output_fingerprint": _stage_output_fingerprint(profile, stage),
                    "completed_at": "2026-07-12T00:00:00+00:00",
                }
            ),
            encoding="utf-8",
        )
    monkeypatch.setattr(automation, "_stage_one_windows_valid", lambda _profile: True)

    plan = build_automation_plan_payload({**raw, "trigger": "resume"})

    assert plan["execution_allowed"] is True
    assert all(stage["plan_action"] == "reuse" for stage in plan["stages"])


def test_partial_mask_blocks_missing_prerequisite(tmp_path: Path) -> None:
    plan = build_automation_plan_payload(
        {**_profile(tmp_path), "execution_mask": [3], "trigger": "resume"}
    )

    assert plan["execution_allowed"] is False
    assert plan["stages"][0]["plan_action"] == "blocked"
    assert plan["stages"][1]["plan_action"] == "blocked"
    assert plan["stages"][2]["plan_action"] == "blocked"


def test_range_reuses_enabled_prerequisite_before_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _profile(tmp_path)
    raw["execution_mask"] = [2, 3, 4, 5, 6, 7]
    profile = normalize_automation_profile(raw)
    stage_one_output = _stage_output_paths(profile, 1)[0]
    stage_one_output.mkdir(parents=True)
    checkpoint_path = _checkpoint_path(profile, 1)
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps(
            {
                "format": AUTOMATION_CHECKPOINT_FORMAT,
                "stage": 1,
                "status": "succeeded",
                "config_hash": _stage_config_hash(profile, 1),
                "output_fingerprint": _stage_output_fingerprint(profile, 1),
                "completed_at": "2026-07-12T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(automation, "_stage_one_windows_valid", lambda _profile: True)

    plan = build_automation_plan_payload({**raw, "trigger": "resume"})

    assert plan["execution_allowed"] is True
    assert plan["stages"][0]["plan_action"] == "reuse"
    assert plan["stages"][1]["plan_action"] == "process"


def test_checkpoint_is_invalid_after_output_changes(tmp_path: Path) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    output = _stage_output_paths(profile, 2)[0]
    output.mkdir(parents=True)
    artifact = output / "part.json"
    artifact.write_text("{}", encoding="utf-8")
    checkpoint_path = _checkpoint_path(profile, 2)
    checkpoint_path.parent.mkdir(parents=True)
    checkpoint_path.write_text(
        json.dumps(
            {
                "format": AUTOMATION_CHECKPOINT_FORMAT,
                "stage": 2,
                "status": "succeeded",
                "config_hash": _stage_config_hash(profile, 2),
                "output_fingerprint": _stage_output_fingerprint(profile, 2),
            }
        ),
        encoding="utf-8",
    )
    assert _load_valid_checkpoint(profile, 2) is not None

    artifact.write_text('{"changed": true}', encoding="utf-8")

    assert _load_valid_checkpoint(profile, 2) is None


def test_window_manifest_validates_body_content_hash(tmp_path: Path) -> None:
    body = tmp_path / "window_post_page_00001.body"
    body.write_bytes(b"first")
    manifest = {
        "format": automation.AUTOMATION_WINDOW_FORMAT,
        "query_hash": "query",
        "complete": True,
        "body_file_count": 1,
        "body_total_bytes": 5,
        "data_hash": _window_body_hash(tmp_path),
    }
    (tmp_path / "automation-window.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert _owned_window_matches(tmp_path, "query") is True

    body.write_bytes(b"other")

    assert _owned_window_matches(tmp_path, "query") is False


def test_stage_seven_passes_compressed_metadata_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    captured: dict[str, object] = {}
    parse_kwargs: dict[str, object] = {}

    def fake_parse(payload: dict[str, object], **kwargs: object) -> dict[str, object]:
        captured.update(payload)
        parse_kwargs.update(kwargs)
        return {"summary": {}}

    monkeypatch.setattr(automation, "parse_disclosure_html_payload", fake_parse)

    cancel_check = lambda: False
    _run_stage(
        7,
        profile,
        trigger="resume",
        progress_callback=None,
        cancel_check=cancel_check,
    )

    assert captured["compressed_metadata_path"] == str(
        tmp_path / "04-external" / "compressed-external-html.json"
    )
    assert "external_metadata_path" not in captured
    assert "cancel_token" not in captured
    assert parse_kwargs["cancel_check"] is cancel_check


def test_stage_two_passes_parent_cancel_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    captured_kwargs: dict[str, object] = {}

    def fake_build(_payload: dict[str, object], **kwargs: object) -> dict[str, object]:
        captured_kwargs.update(kwargs)
        return {"summary": {}}

    monkeypatch.setattr(automation, "build_disclosure_table_payload", fake_build)
    cancel_check = lambda: False

    _run_stage(
        2,
        profile,
        trigger="resume",
        progress_callback=None,
        cancel_check=cancel_check,
    )

    assert captured_kwargs["cancel_check"] is cancel_check


def test_content_download_rate_limits_each_actual_kind_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = {"now": 100.0}
    sleeps: list[float] = []

    class Response:
        content = b"<html>ok</html>"

        def raise_for_status(self) -> None:
            return None

    class Session:
        def __enter__(self) -> "Session":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def get(self, *_args: object, **_kwargs: object) -> Response:
            return Response()

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(html_content_download.requests, "Session", Session)
    monkeypatch.setattr(
        html_content_download, "search_paths", lambda _content: {"doc_loc_path": "https://kind.krx.co.kr/body"}
    )
    monkeypatch.setattr("time.time", lambda: clock["now"])
    monkeypatch.setattr("time.sleep", sleep)

    saved = html_content_download.download_disclosure_content_htmls(
        output_directory=tmp_path,
        request_headers={},
        targets=[{"acpt_no": "20260712000001", "doc_no": "1"}],
        max_requests_per_minute=30,
    )

    assert len(saved) == 1
    assert sleeps == [2.0]


def test_automation_plan_api_exposes_stage_preflight(tmp_path: Path) -> None:
    response = TestClient(app).post(
        "/api/disclosure-workflows/plan",
        json={**_profile(tmp_path), "trigger": "sync"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["execution_allowed"] is True
    assert [stage["stage"] for stage in payload["stages"]] == list(range(1, 8))


def test_recent_window_refresh_detects_content_change_not_page_position(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _profile(tmp_path)
    raw["decisions"]["s1_search"]["start_date"] = "2026-07-12"  # type: ignore[index]
    profile = normalize_automation_profile(raw)

    def fake_run_single(payload: dict[str, object], **_kwargs: object) -> dict[str, object]:
        output = Path(str(payload["output_directory"]))
        output.mkdir(parents=True, exist_ok=True)
        (output / "001_post_page_00001.body").write_bytes(b"same disclosure rows")
        return {
            "download_status": {"integrity_valid": True},
            "summary": {"success": 1, "failed": 0, "total": 1},
        }

    monkeypatch.setattr(automation, "_run_single", fake_run_single)
    monkeypatch.setattr(automation.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        automation,
        "disclosure_file_rows",
        lambda path: [{"body": Path(path).read_text("utf-8")}],
    )
    first = automation._run_stage_one(
        profile,
        trigger="sync",
        progress_callback=lambda _message: None,
        cancel_check=lambda: False,
    )
    second = automation._run_stage_one(
        profile,
        trigger="sync",
        progress_callback=lambda _message: None,
        cancel_check=lambda: False,
    )

    assert first["changed_windows"] == 1
    assert second["changed_windows"] == 0
    assert second["refreshed_windows"] == 1


def test_active_html_candidate_reuses_only_current_membership(tmp_path: Path) -> None:
    current = tmp_path / "current"
    temporary = tmp_path / "candidate"
    (current / "2026").mkdir(parents=True)
    keep_html = "<html><body>" + ("keep " * 30) + "</body></html>"
    stale_html = "<html><body>" + ("stale " * 30) + "</body></html>"
    (current / "2026" / "20260712000001.html").write_text(keep_html, encoding="utf-8")
    (current / "2026" / "20260712000002.html").write_text(stale_html, encoding="utf-8")

    copied = automation._copy_reusable_active_html(
        current,
        temporary,
        [("20260712000001", "2026")],
    )

    assert copied == 1
    assert (temporary / "2026" / "20260712000001.html").read_text("utf-8") == keep_html
    assert not (temporary / "2026" / "20260712000002.html").exists()


def test_stage_four_replaces_active_membership_without_stale_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    filtered_path = tmp_path / "03-filter" / "filtered.json"
    filtered_path.parent.mkdir(parents=True)

    def write_filtered(acpt_numbers: list[str]) -> None:
        filtered_path.write_text(
            json.dumps(
                {
                    "disclosures": [
                        {"acpt_no": acpt_no, "disclosed_at": "2026-07-12 09:00"}
                        for acpt_no in acpt_numbers
                    ]
                }
            ),
            encoding="utf-8",
        )

    def fake_download(body: dict[str, object], **_kwargs: object) -> dict[str, object]:
        source = json.loads(Path(str(body["source_json_path"])).read_text("utf-8"))
        output = Path(str(body["output_directory"]))
        acpt_numbers = [record["acpt_no"] for record in source["disclosures"]]
        for acpt_no in acpt_numbers:
            path = output / "2026" / f"{acpt_no}.html"
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(
                    "<html><body>" + (f"{acpt_no} " * 20) + "</body></html>",
                    encoding="utf-8",
                )
        return {
            "requested_count": len(acpt_numbers),
            "saved_count": len(acpt_numbers),
            "cancelled": False,
        }

    def fake_compress(body: dict[str, object], **_kwargs: object) -> dict[str, object]:
        directory = Path(str(body["input_directory"]))
        records = [
            {"acpt_no": path.stem, "docs": []}
            for path in sorted(directory.rglob("*.html"))
        ]
        (directory / "compressed-external-html.json").write_text(
            json.dumps({"records": records}), encoding="utf-8"
        )
        return {"summary": {"compressed_files": len(records)}}

    monkeypatch.setattr(automation, "download_disclosure_html_payload", fake_download)
    monkeypatch.setattr(
        automation, "compress_disclosure_external_html_payload", fake_compress
    )

    write_filtered(["20260712000001", "20260712000002"])
    automation._run_stage(
        4,
        profile,
        trigger="sync",
        progress_callback=lambda _message: None,
        cancel_check=lambda: False,
    )
    write_filtered(["20260712000001"])
    automation._run_stage(
        4,
        profile,
        trigger="sync",
        progress_callback=lambda _message: None,
        cancel_check=lambda: False,
    )

    current = tmp_path / "04-external" / ".automation-current"
    assert [path.stem for path in current.rglob("*.html")] == ["20260712000001"]
    compressed = json.loads(
        (tmp_path / "04-external" / "compressed-external-html.json").read_text(
            "utf-8"
        )
    )
    assert [record["acpt_no"] for record in compressed["records"]] == [
        "20260712000001"
    ]
