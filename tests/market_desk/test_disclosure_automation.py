from __future__ import annotations

import json
from pathlib import Path

import pytest

from finiq.market_desk.web.features.disclosure_workflow import automation
from finiq.market_desk.web.features.disclosure_workflow.automation import (
    _run_stage,
    _run_stage_one,
    _stage_output_paths,
    build_automation_plan_payload,
    normalize_automation_profile,
    run_disclosure_automation_payload,
)


def _profile(root: Path, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "테스트 자동화",
        "data_root": str(root),
        "steps": {
            "s1_download": True,
            "s2_table": True,
            "s3_filter": True,
            "s4_external_html_download": True,
            "s5_internal_html_download": True,
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
            "s6_sections": {"unmatched_policy": "automatic"},
        },
        "execution": {
            "mode": "bond_issuance",
            "parser_method": "bond_issuance",
            "page_size": 100,
            "local_workers": 4,
            "progress_interval": 25,
            "timeout": 20,
        },
    }
    payload.update(overrides)
    return payload


def _callbacks() -> dict[str, object]:
    return {
        "trigger": "sync",
        "progress_callback": lambda _message: None,
        "cancel_check": lambda: False,
    }


def test_normalize_automation_profile_locks_shared_execution_settings(
    tmp_path: Path,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))

    assert profile["data_root"] == str(tmp_path.resolve())
    assert profile["execution"]["max_requests_per_minute"] == 45
    assert profile["execution"]["progress_interval"] == 25
    assert profile["decisions"]["s6_sections"] == {
        "unmatched_policy": "automatic",
        "section_save_rules": {},
    }


def test_normalize_automation_profile_rejects_last_report_only(
    tmp_path: Path,
) -> None:
    payload = _profile(tmp_path)
    payload["decisions"]["s1_search"]["last_report_only"] = True  # type: ignore[index]

    with pytest.raises(ValueError, match="최종보고서만"):
        normalize_automation_profile(payload)


@pytest.mark.parametrize("trigger", ["sync", "resume"])
def test_plan_runs_selected_stages_in_order(tmp_path: Path, trigger: str) -> None:
    plan = build_automation_plan_payload({**_profile(tmp_path), "trigger": trigger})

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


def test_stage_output_paths_are_canonical_and_honor_stage_links(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "local"
    target_root = tmp_path / "target"
    for stage_name in (
        "01-list",
        "02-table",
        "04-external-html-download",
        "04-external-html-compress",
        "05-internal-html-download",
        "06-sections",
    ):
        local_stage = data_root / stage_name
        local_stage.mkdir(parents=True)
        (target_root / stage_name).mkdir(parents=True)
        (local_stage / "finiq-stage-link.json").write_text(
            json.dumps(
                {
                    "format": "finiq_stage_link_v1",
                    "schema_version": 1,
                    "target_workspace": str(target_root),
                }
            ),
            encoding="utf-8",
        )
    profile = normalize_automation_profile(_profile(data_root))

    assert _stage_output_paths(profile, 1) == [target_root / "01-list"]
    assert _stage_output_paths(profile, 2) == [target_root / "02-table"]
    assert _stage_output_paths(profile, 4) == [
        target_root
        / "04-external-html-compress"
        / "bond_issuance"
        / "compressed-external-html.json",
        target_root / "04-external-html-download" / "bond_issuance",
    ]
    assert _stage_output_paths(profile, 5) == [
        target_root / "05-internal-html-download" / "bond_issuance"
    ]
    assert _stage_output_paths(profile, 6) == [
        target_root / "06-sections" / "bond_issuance"
    ]


def test_stage_one_calls_regular_download_service_with_official_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    captured: dict[str, object] = {}

    def run_download(body: dict[str, object], **_kwargs: object) -> dict[str, object]:
        captured.update(body)
        return {"mode": "yearly", "summary": {"success": 1}}

    monkeypatch.setattr(automation, "run_download_action", run_download)

    result = _run_stage_one(profile, **_callbacks())

    assert result["mode"] == "yearly"
    assert captured["output_directory"] == str(tmp_path / "01-list")
    assert captured["mode"] == "yearly"


def test_stage_one_uses_regular_existing_check_before_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    folder = tmp_path / "01-list" / "20260101_20260712"
    folder.mkdir(parents=True)
    (folder / "001_post_page_00001.body").write_text("saved", encoding="utf-8")
    calls: list[str] = []

    def check_existing(path: str, **_kwargs: object) -> dict[str, object]:
        calls.append(path)
        return {
            "has_existing": True,
            "ranges": [
                {
                    "status": "stale",
                    "local_count": 100,
                    "kind_count": 101,
                    "error_detail": "KIND 현재 건수가 다릅니다.",
                }
            ],
        }

    monkeypatch.setattr(automation, "check_existing_downloads", check_existing)
    monkeypatch.setattr(
        automation,
        "run_download_action",
        lambda *_args, **_kwargs: pytest.fail("확인 전 다운로드하면 안 됩니다."),
    )

    pending = _run_stage_one(profile, **_callbacks())

    assert calls == [str(folder)]
    assert pending["needs_download_confirmation"] is True
    assert pending["download_conflicts"] == [
        {
            "range": folder.name,
            "code": "kind_count_changed",
            "saved_count": 100,
            "kind_count": 101,
            "reason": "KIND 현재 건수가 다릅니다.",
        }
    ]

    profile["download_confirmation"] = pending["download_confirmation"]
    monkeypatch.setattr(
        automation,
        "run_download_action",
        lambda *_args, **_kwargs: {"mode": "yearly"},
    )

    completed = _run_stage_one(profile, **_callbacks())

    assert completed["mode"] == "yearly"


def test_stage_one_asks_before_replacing_downloads_with_unusable_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    folder = tmp_path / "01-list" / "20260101_20260712"
    folder.mkdir(parents=True)
    (folder / "001_post_page_00001.body").write_text("saved", encoding="utf-8")

    def fail_existing_check(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise automation.DownloadInputMetadataError(
            "저장 조건을 읽을 수 없습니다."
        )

    monkeypatch.setattr(
        automation,
        "check_existing_downloads",
        fail_existing_check,
    )
    monkeypatch.setattr(
        automation,
        "run_download_action",
        lambda *_args, **_kwargs: pytest.fail("확인 전 다운로드하면 안 됩니다."),
    )

    pending = _run_stage_one(profile, **_callbacks())

    assert pending["needs_download_confirmation"] is True
    assert pending["download_conflicts"] == [
        {
            "range": folder.name,
            "code": "saved_download_invalid",
            "saved_count": None,
            "kind_count": None,
            "reason": "저장 조건을 읽을 수 없습니다.",
        }
    ]


def test_stage_two_reads_official_stage_one_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    captured: dict[str, object] = {}

    def build_table(body: dict[str, object], **_kwargs: object) -> dict[str, object]:
        captured.update(body)
        return {"summary": {}}

    monkeypatch.setattr(automation, "build_disclosure_table_payload", build_table)

    _run_stage(2, profile, **_callbacks())

    assert captured["root_directory"] == str(tmp_path / "01-list")
    assert captured["output_path"] == str(tmp_path / "02-table")


def test_stage_three_uses_regular_filter_workflow_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    captured: dict[str, object] = {}
    result = {
        "format": "kind_disclosure_filter_v1",
        "summary": {},
        "disclosures": [],
    }

    def run_filter_workflow(
        body: dict[str, object], **_kwargs: object
    ) -> dict[str, object]:
        captured.update(body)
        return result

    monkeypatch.setattr(
        automation,
        "run_filter_workflow_payload",
        run_filter_workflow,
    )

    returned = _run_stage(3, profile, **_callbacks())

    assert returned is result
    assert captured["data_root"] == str(tmp_path)
    assert captured["mode"] == "bond_issuance"
    assert captured["filter_blocks"] == []


def test_stage_four_uses_official_mode_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    download_body: dict[str, object] = {}
    compress_body: dict[str, object] = {}

    def download(body: dict[str, object], **_kwargs: object) -> dict[str, object]:
        download_body.update(body)
        return {"cancelled": False}

    def compress(body: dict[str, object], **_kwargs: object) -> dict[str, object]:
        compress_body.update(body)
        return {"verification": {"passed": True}}

    monkeypatch.setattr(automation, "download_disclosure_external_html_payload", download)
    monkeypatch.setattr(automation, "compress_disclosure_external_html_payload", compress)

    _run_stage(4, profile, **_callbacks())

    external = tmp_path / "04-external-html-download" / "bond_issuance"
    compressed = tmp_path / "04-external-html-compress" / "bond_issuance"
    assert download_body["output_directory"] == str(external)
    assert compress_body["input_directory"] == str(external)
    assert compress_body["output_directory"] == str(compressed)


def test_stage_five_uses_official_mode_directory_and_public_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    captured_body: dict[str, object] = {}
    captured_kwargs: dict[str, object] = {}

    def download(
        body: dict[str, object], **kwargs: object
    ) -> dict[str, object]:
        captured_body.update(body)
        captured_kwargs.update(kwargs)
        return {"cancelled": False}

    monkeypatch.setattr(automation, "download_disclosure_internal_html_payload", download)

    _run_stage(5, profile, **_callbacks())

    assert captured_body["source_compressed_json_path"] == str(
        tmp_path
        / "04-external-html-compress"
        / "bond_issuance"
        / "compressed-external-html.json"
    )
    assert captured_body["output_directory"] == str(
        tmp_path / "05-internal-html-download" / "bond_issuance"
    )
    assert captured_kwargs["confirm_source_unavailable"] is True


def test_stage_six_uses_official_mode_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    captured: dict[str, object] = {}

    def save_sections(body: dict[str, object], **_kwargs: object) -> dict[str, object]:
        captured.update(body)
        return {"cancelled": False, "summary": {"integrity_ok": True}}

    monkeypatch.setattr(automation, "save_disclosure_html_sections_payload", save_sections)

    _run_stage(6, profile, **_callbacks())

    assert captured["input_directory"] == str(
        tmp_path / "05-internal-html-download" / "bond_issuance"
    )
    assert captured["output_directory"] == str(
        tmp_path / "06-sections" / "bond_issuance"
    )


def test_automation_stops_before_later_stages_until_redownload_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[int] = []

    def run_stage(stage: int, *_args: object, **_kwargs: object) -> dict[str, object]:
        executed.append(stage)
        if stage != 1:
            pytest.fail("확인 전 다음 단계를 시작하면 안 됩니다.")
        return {
            "needs_download_confirmation": True,
            "download_conflicts": [{"range": "2026", "reason": "건수 충돌"}],
            "download_confirmation": "token",
        }

    monkeypatch.setattr(automation, "_run_stage", run_stage)

    result = run_disclosure_automation_payload(_profile(tmp_path))

    assert executed == [1]
    assert result["workflow_status"] == "needs_download_confirmation"
    assert result["download_confirmation"] == "token"
