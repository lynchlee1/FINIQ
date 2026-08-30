"""Regression tests for atomic KIND automatic downloads."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from finiq.data_scraper.core.client import SEARCH_RESULTS_FILENAME_TEMPLATE
from finiq.market_desk.web.features.downloads import kind_runner


def _result_page_html(
    *,
    page_number: int,
    changed_first_page: bool = False,
) -> bytes:
    item_no = 99 if changed_first_page else page_number
    return (
        f"""
        <html><body>
          <section class="paging-group">
            <div class="paging type-00">
              전체 <em>3</em>건 : <strong>{page_number}</strong>/3
            </div>
          </section>
          <table class="list" summary="번호, 일시, 회사명, 공시제목, 제출인">
            <tbody><tr>
              <td>{item_no}</td>
              <td>2025-01-01 09:00</td>
              <td><a id="companysum" title="테스트회사" onclick="companysummary_open('000001')">테스트회사</a></td>
              <td><a title="테스트 공시 {item_no}" onclick="openDisclsViewer('20250101{item_no:06d}','')">테스트 공시 {item_no}</a></td>
              <td>테스트제출인</td>
            </tr></tbody>
          </table>
        </body></html>
        """
    ).encode("utf-8")


class _FakeDownloadPages:
    def __init__(
        self,
        *,
        fail_once_at_page: int | None = None,
        change_verification_page: bool = False,
    ) -> None:
        self.fail_once_at_page = fail_once_at_page
        self.change_verification_page = change_verification_page
        self.failed = False
        self.page_one_calls = 0
        self.ranges: list[tuple[int, int]] = []

    def __call__(self, **kwargs: Any) -> None:
        output_directory = Path(kwargs["output_directory"])
        output_directory.mkdir(parents=True, exist_ok=True)
        start_page = int(kwargs["start_page"])
        end_page = int(kwargs["end_page"])
        self.ranges.append((start_page, end_page))

        main_path = output_directory / "000_mainGET.body"
        main_path.write_bytes(b"main")
        validator = kwargs.get("saved_file_validator")
        callback = kwargs.get("saved_file_callback")
        if validator is not None:
            validator(main_path, None, None)
        if callback is not None:
            callback(main_path, None, None)

        for page_number in range(start_page, end_page + 1):
            if page_number == 1:
                self.page_one_calls += 1
            changed_first_page = (
                page_number == 1
                and self.page_one_calls > 1
                and self.change_verification_page
            )
            page_path = output_directory / SEARCH_RESULTS_FILENAME_TEMPLATE.format(
                page_number=page_number
            )
            page_path.write_bytes(
                _result_page_html(
                    page_number=page_number,
                    changed_first_page=changed_first_page,
                )
            )
            request_data = [("pageIndex", str(page_number))]
            if validator is not None:
                validator(page_path, page_number, request_data)
            if callback is not None:
                callback(page_path, page_number, request_data)
            if (
                page_number == self.fail_once_at_page
                and not self.failed
            ):
                self.failed = True
                raise RuntimeError("interrupted")


def _run_auto_download(output_directory: Path) -> None:
    kind_runner._run_auto_download_staged(
        output_directory=output_directory,
        payload={},
        start_date="2025-01-01",
        end_date="2025-12-31",
        page_size=1,
        wait_seconds=0,
        timeout=5,
        search_filters=None,
        disclosure_type_groups=None,
        last_report_only=None,
        page_worker_count=1,
        progress_callback=None,
        cancel_check=None,
    )


def _patch_download_pages(
    monkeypatch: pytest.MonkeyPatch,
    fake_download: _FakeDownloadPages,
) -> None:
    monkeypatch.setattr(kind_runner, "download_pages", fake_download)
    monkeypatch.setattr(
        "finiq.data_scraper.workflow.workflow.download_pages",
        fake_download,
    )


def test_auto_download_resumes_staging_and_publishes_only_complete_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_directory = tmp_path / "01-list"
    output_directory.mkdir()
    previous_file = output_directory / "previous.txt"
    previous_file.write_text("keep until publish", encoding="utf-8")
    fake_download = _FakeDownloadPages(fail_once_at_page=2)
    _patch_download_pages(monkeypatch, fake_download)

    with pytest.raises(RuntimeError, match="interrupted"):
        _run_auto_download(output_directory)

    assert previous_file.read_text(encoding="utf-8") == "keep until publish"
    staging_directory = kind_runner._download_staging_directory(output_directory)
    assert sorted(path.name for path in staging_directory.glob("*_post_page_*.body")) == [
        "001_post_page_00001.body",
        "002_post_page_00002.body",
    ]
    interrupted_checkpoint = json.loads(
        (staging_directory / "kind_workflow.checkpoint.json").read_text(
            encoding="utf-8"
        )
    )
    assert interrupted_checkpoint["completed"] is False
    assert interrupted_checkpoint["last_saved_page"] == 2

    _run_auto_download(output_directory)

    assert fake_download.ranges == [(1, 1), (2, 3), (3, 3), (1, 1)]
    assert not staging_directory.exists()
    assert not previous_file.exists()
    assert len(list(output_directory.glob("*_post_page_*.body"))) == 3
    input_snapshot = json.loads(
        (output_directory / "kind_workflow.input.json").read_text(encoding="utf-8")
    )
    checkpoint = json.loads(
        (output_directory / "kind_workflow.checkpoint.json").read_text(
            encoding="utf-8"
        )
    )
    assert "start_page" not in input_snapshot
    assert "request_headers" not in input_snapshot
    assert "end_page" not in input_snapshot
    assert "wait_seconds_between_requests" not in input_snapshot
    assert "timeout" not in input_snapshot
    assert "parse_mode" not in input_snapshot
    assert "request_headers" not in checkpoint["input"]
    assert checkpoint["completed"] is True
    assert checkpoint["last_saved_page"] == 3


def test_auto_download_resumes_from_first_missing_staged_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_directory = tmp_path / "01-list"
    fake_download = _FakeDownloadPages(fail_once_at_page=2)
    _patch_download_pages(monkeypatch, fake_download)

    with pytest.raises(RuntimeError, match="interrupted"):
        _run_auto_download(output_directory)

    staging_directory = kind_runner._download_staging_directory(output_directory)
    page_two = staging_directory / SEARCH_RESULTS_FILENAME_TEMPLATE.format(page_number=2)
    page_three = staging_directory / SEARCH_RESULTS_FILENAME_TEMPLATE.format(page_number=3)
    page_two.unlink()
    page_three.write_bytes(_result_page_html(page_number=3))
    checkpoint_path = staging_directory / "kind_workflow.checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["saved_files"] = [
        name
        for name in checkpoint["saved_files"]
        if Path(name).name != page_two.name
    ] + [page_three.name]
    checkpoint["last_saved_page"] = 3
    checkpoint["last_saved_file"] = page_three.name
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    _run_auto_download(output_directory)

    assert fake_download.ranges == [(1, 1), (2, 3), (2, 3), (1, 1)]
    assert len(list(output_directory.glob("*_post_page_*.body"))) == 3


def test_auto_download_consistency_failure_preserves_previous_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_directory = tmp_path / "01-list"
    output_directory.mkdir()
    previous_file = output_directory / "previous.txt"
    previous_file.write_text("do not replace", encoding="utf-8")
    fake_download = _FakeDownloadPages(change_verification_page=True)
    _patch_download_pages(monkeypatch, fake_download)

    with pytest.raises(ValueError, match="다운로드 중 변경되었습니다"):
        _run_auto_download(output_directory)

    assert fake_download.ranges == [(1, 1), (2, 3), (1, 1)]
    assert previous_file.read_text(encoding="utf-8") == "do not replace"
    assert kind_runner._download_staging_directory(output_directory).is_dir()
    assert not list(tmp_path.glob(".01-list.kind-download-backup-*"))


def test_download_publish_cleanup_failure_is_reported_without_failing_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_directory = tmp_path / "01-list"
    output_directory.mkdir()
    (output_directory / "old.txt").write_text("old", encoding="utf-8")
    staging_directory = kind_runner._download_staging_directory(output_directory)
    staging_directory.mkdir()
    (staging_directory / "new.txt").write_text("new", encoding="utf-8")
    original_rmtree = kind_runner.shutil.rmtree

    def fail_backup_cleanup(path: Path) -> None:
        if ".kind-download-backup-" in Path(path).name:
            raise OSError("simulated cleanup failure")
        original_rmtree(path)

    monkeypatch.setattr(kind_runner.shutil, "rmtree", fail_backup_cleanup)

    warnings = kind_runner._publish_staged_download(
        staging_directory, output_directory
    )

    assert (output_directory / "new.txt").read_text(encoding="utf-8") == "new"
    assert not (output_directory / "old.txt").exists()
    assert len(warnings) == 1
    assert "게시에는 성공" in warnings[0]
    assert list(tmp_path.glob(".01-list.kind-download-backup-*"))
