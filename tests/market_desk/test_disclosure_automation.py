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


def test_normalize_automation_profile_uses_canonical_disclosure_type_set(
    tmp_path: Path,
) -> None:
    first = _profile(tmp_path)
    first["decisions"]["s1_search"]["disclosure_type_groups"] = {  # type: ignore[index]
        "01": ["0172", "0161", "0161"]
    }
    second = json.loads(json.dumps(first))
    second["decisions"]["s1_search"]["disclosure_type_groups"] = [  # type: ignore[index]
        "invalid-shape"
    ]

    normalized = normalize_automation_profile(first)
    assert normalized["decisions"]["s1_search"]["disclosure_type_groups"] == {
        "01": ["0161", "0172"]
    }
    with pytest.raises(ValueError, match="disclosure_type_groups must be an object"):
        normalize_automation_profile(second)

    invalid = json.loads(json.dumps(first))
    invalid["decisions"]["s1_search"]["disclosure_type_groups"] = {  # type: ignore[index]
        "01": ["not-a-kind-code"]
    }
    with pytest.raises(ValueError, match="unsupported disclosure_type_groups.01"):
        normalize_automation_profile(invalid)


def test_stage_hash_ignores_operational_settings_but_keeps_page_size(
    tmp_path: Path,
) -> None:
    base_payload = _profile(tmp_path)
    changed_operations = json.loads(json.dumps(base_payload))
    changed_operations["execution"].update(
        {
            "local_workers": 8,
            "progress_interval": 100,
            "timeout": 60,
        }
    )
    changed_page_size = json.loads(json.dumps(base_payload))
    changed_page_size["execution"]["page_size"] = 50
    base = normalize_automation_profile(base_payload)

    assert automation._stage_config_hash(
        base, 1
    ) == automation._stage_config_hash(
        normalize_automation_profile(changed_operations), 1
    )
    assert automation._profile_semantic_hash(
        base
    ) == automation._profile_semantic_hash(
        normalize_automation_profile(changed_operations)
    )
    assert automation._stage_config_hash(
        base, 1
    ) != automation._stage_config_hash(
        normalize_automation_profile(changed_page_size), 1
    )
    assert automation._profile_semantic_hash(
        base
    ) != automation._profile_semantic_hash(
        normalize_automation_profile(changed_page_size)
    )


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


def test_stage_one_blocks_conflicting_download_outside_requested_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    current_folder = tmp_path / "01-list" / "20260101_20260712"
    outside_folder = tmp_path / "01-list" / "20250101_20251231"
    for folder in (current_folder, outside_folder):
        folder.mkdir(parents=True)
        (folder / "001_post_page_00001.body").write_text("saved", encoding="utf-8")
    calls: list[str] = []

    def check_existing(path: str, **_kwargs: object) -> dict[str, object]:
        calls.append(path)
        filters_match = Path(path) == current_folder
        return {
            "has_existing": True,
            "ranges": [
                {
                    "status": "validated",
                    "filters_match": filters_match,
                    "local_count": 100,
                    "kind_count": 100,
                    "error_detail": (
                        None if filters_match else "현재 검색 설정과 다릅니다."
                    ),
                }
            ],
        }

    monkeypatch.setattr(automation, "check_existing_downloads", check_existing)
    monkeypatch.setattr(
        automation,
        "run_download_action",
        lambda *_args, **_kwargs: pytest.fail(
            "요청 범위 밖 충돌을 남긴 채 다운로드하면 안 됩니다."
        ),
    )

    with pytest.raises(ValueError, match="현재 요청 기간 밖"):
        _run_stage_one(profile, **_callbacks())

    assert set(calls) == {str(current_folder), str(outside_folder)}


def test_stage_one_holds_kind_network_lock_for_check_and_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    folder = tmp_path / "01-list" / "20260101_20260712"
    folder.mkdir(parents=True)
    (folder / "001_post_page_00001.body").write_text("saved", encoding="utf-8")
    events: list[str] = []

    class TrackingLock:
        held = False

        def __enter__(self) -> None:
            self.held = True
            events.append("lock")

        def __exit__(self, *_args: object) -> None:
            self.held = False
            events.append("unlock")

    lock = TrackingLock()

    def check_existing(*_args: object, **_kwargs: object) -> dict[str, object]:
        assert lock.held is True
        events.append("check")
        return {
            "has_existing": True,
            "ranges": [{"status": "validated", "filters_match": True}],
        }

    def run_download(*_args: object, **_kwargs: object) -> dict[str, object]:
        assert lock.held is True
        events.append("download")
        return {"mode": "yearly"}

    monkeypatch.setattr(automation, "KIND_NETWORK_JOB_LOCK", lock)
    monkeypatch.setattr(automation, "check_existing_downloads", check_existing)
    monkeypatch.setattr(automation, "run_download_action", run_download)

    result = _run_stage_one(profile, **_callbacks())

    assert result["mode"] == "yearly"
    assert events == ["lock", "check", "download", "unlock"]


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


def test_stage_five_uses_official_mode_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    captured_body: dict[str, object] = {}

    def download(
        body: dict[str, object], **_kwargs: object
    ) -> dict[str, object]:
        captured_body.update(body)
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


def test_automation_completes_after_empty_stage_three_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executed: list[int] = []

    def run_stage(stage: int, *_args: object, **_kwargs: object) -> dict[str, object]:
        executed.append(stage)
        if stage == 3:
            return {"disclosures": [], "summary": {"returned_disclosures": 0}}
        if stage > 3:
            pytest.fail("조건에 맞는 공시가 없으면 04 이후를 실행하면 안 됩니다.")
        return {"summary": {}}

    monkeypatch.setattr(automation, "_run_stage", run_stage)

    result = run_disclosure_automation_payload(_profile(tmp_path))

    assert executed == [1, 2, 3]
    assert result["workflow_status"] == "completed"
    assert result["completion_reason"] == "조건에 맞는 공시 없음"
    assert result["output_path"] == ""
    assert [stage["status"] for stage in result["stages"]] == [
        "succeeded",
        "succeeded",
        "succeeded",
        "skipped",
        "skipped",
        "skipped",
        "skipped",
    ]


def test_automation_does_not_treat_malformed_stage_three_result_as_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def run_stage(stage: int, *_args: object, **_kwargs: object) -> dict[str, object]:
        return {"summary": {}}

    monkeypatch.setattr(automation, "_run_stage", run_stage)

    with pytest.raises(ValueError, match="disclosures must be a list"):
        run_disclosure_automation_payload(_profile(tmp_path))
    assert not (
        tmp_path / ".finiq" / "disclosure-automation" / "checkpoints" / "stage-3.json"
    ).exists()


def test_automation_stops_after_reused_empty_stage_three_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = normalize_automation_profile(_profile(tmp_path))
    stages = [
        {
            "stage": stage,
            "label": automation.STAGE_LABELS[stage],
            "plan_action": "reuse" if stage <= 3 else "process",
        }
        for stage in automation.STAGE_NUMBERS
    ]
    monkeypatch.setattr(
        automation,
        "build_automation_plan_payload",
        lambda _payload: {
            "execution_allowed": True,
            "profile": profile,
            "profile_hash": "profile-hash",
            "trigger": "resume",
            "stages": stages,
        },
    )
    monkeypatch.setattr(
        automation,
        "load_filter_workflow_result_payload",
        lambda **_kwargs: {"disclosures": []},
    )
    monkeypatch.setattr(
        automation,
        "_run_stage",
        lambda *_args, **_kwargs: pytest.fail("재사용한 빈 결과 뒤 단계를 실행하면 안 됩니다."),
    )

    result = run_disclosure_automation_payload(_profile(tmp_path))

    assert result["workflow_status"] == "completed"
    assert result["completion_reason"] == "조건에 맞는 공시 없음"
    assert [stage["status"] for stage in result["stages"]] == [
        "reused",
        "reused",
        "reused",
        "skipped",
        "skipped",
        "skipped",
        "skipped",
    ]
