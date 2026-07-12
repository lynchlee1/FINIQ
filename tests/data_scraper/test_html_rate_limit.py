from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

import finiq.data_scraper.core.html_rate_limit as rate_limit_module
import finiq.market_desk.web.features.disclosures.html_content_download as content_module
from finiq.data_scraper.core.client import download_disclosure_viewer_htmls


class _RecordingLimiter:
    def __init__(self) -> None:
        self.calls = 0

    def wait(self, cancel_check=None) -> bool:
        self.calls += 1
        return bool(cancel_check is not None and cancel_check())


class _ViewerResponse:
    def __init__(self) -> None:
        self.content = ("<html><body>" + ("viewer " * 30) + "</body></html>").encode()

    def raise_for_status(self) -> None:
        return None

    def close(self) -> None:
        return None


class _ViewerSession:
    def get(self, *args: Any, **kwargs: Any) -> _ViewerResponse:
        return _ViewerResponse()


def test_sliding_window_limiter_waits_after_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert rate_limit_module.HTML_DOWNLOAD_MAX_REQUESTS_PER_MINUTE == 100
    clock = [0.0]
    limiter = rate_limit_module.SlidingWindowRateLimiter(2)

    monkeypatch.setattr(rate_limit_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        rate_limit_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    assert limiter.wait() is False
    assert limiter.wait() is False
    assert limiter.wait() is False
    assert clock[0] >= 60


def test_external_and_content_html_share_one_request_limiter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = _RecordingLimiter()
    monkeypatch.setattr(rate_limit_module, "_HTML_DOWNLOAD_RATE_LIMITER", limiter)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    external_paths = download_disclosure_viewer_htmls(
        output_directory=tmp_path / "external",
        request_headers={},
        acpt_numbers=["20260101000001"],
        session=_ViewerSession(),
        max_requests_per_minute=100,
        max_workers=1,
        max_retries=0,
    )

    def fake_fetch_content_html(
        *args: Any,
        before_request=None,
        **kwargs: Any,
    ) -> bytes:
        assert before_request is not None
        before_request()
        before_request()
        return ("<html><body>" + ("content " * 30) + "</body></html>").encode()

    monkeypatch.setattr(content_module, "_fetch_content_html", fake_fetch_content_html)
    content_paths = content_module.download_disclosure_content_htmls(
        output_directory=tmp_path / "content",
        request_headers={},
        targets=[{"acpt_no": "20260101000002", "doc_no": "20260101000003"}],
        max_requests_per_minute=100,
        skip_existing=False,
    )

    assert len(external_paths) == 1
    assert len(content_paths) == 1
    assert limiter.calls == 3
