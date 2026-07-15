from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest

import finiq.data_scraper.core.html_rate_limit as rate_limit_module
import finiq.market_desk.web.features.disclosures.internal_html_download as internal_module
from finiq.data_scraper.core.client import download_disclosure_external_htmls


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


def test_sliding_window_limiter_rejects_non_positive_capacity() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        rate_limit_module.SlidingWindowRateLimiter(0)


def test_external_and_content_html_share_one_request_limiter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limiter = rate_limit_module.SlidingWindowRateLimiter(100)
    monkeypatch.setattr(rate_limit_module, "_HTML_DOWNLOAD_RATE_LIMITER", limiter)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    external_paths = download_disclosure_external_htmls(
        output_directory=tmp_path / "external",
        request_headers={},
        acpt_numbers=["20260101000001"],
        session=_ViewerSession(),
        max_requests_per_minute=100,
        max_workers=1,
        max_retries=0,
    )

    def fake_fetch_internal_html(
        *args: Any,
        before_request=None,
        **kwargs: Any,
    ) -> bytes:
        assert before_request is not None
        before_request()
        before_request()
        return ("<html><body>" + ("content " * 30) + "</body></html>").encode()

    monkeypatch.setattr(internal_module, "_fetch_internal_html", fake_fetch_internal_html)
    internal_paths = internal_module.download_disclosure_internal_htmls(
        output_directory=tmp_path / "content",
        request_headers={},
        targets=[{"acpt_no": "20260101000002", "doc_no": "20260101000003"}],
        max_requests_per_minute=100,
        skip_existing=False,
    )

    assert len(external_paths) == 1
    assert len(internal_paths) == 1
    assert len(limiter._request_timestamps) == 3


def test_local_and_global_windows_reserve_the_same_request_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    local = rate_limit_module.SlidingWindowRateLimiter(2)
    global_limiter = rate_limit_module.SlidingWindowRateLimiter(1)
    monkeypatch.setattr(rate_limit_module, "_HTML_DOWNLOAD_RATE_LIMITER", global_limiter)
    monkeypatch.setattr(rate_limit_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        rate_limit_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    assert rate_limit_module.wait_for_html_download_request_slot(
        local_limiter=local
    ) is False
    assert rate_limit_module.wait_for_html_download_request_slot(
        local_limiter=local
    ) is False

    assert clock[0] >= 60
    assert local._request_timestamps == global_limiter._request_timestamps


def test_spacing_is_reserved_after_a_global_window_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [0.0]
    request_times: list[float] = []
    global_limiter = rate_limit_module.SlidingWindowRateLimiter(2)
    global_limiter._request_timestamps = [0.0, 0.0]
    spacing_limiter = rate_limit_module.RequestSpacingLimiter(2.0)
    monkeypatch.setattr(rate_limit_module, "_HTML_DOWNLOAD_RATE_LIMITER", global_limiter)
    monkeypatch.setattr(rate_limit_module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        rate_limit_module.time,
        "sleep",
        lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    for _ in range(2):
        assert rate_limit_module.wait_for_html_download_request_slot(
            spacing_limiter=spacing_limiter
        ) is False
        request_times.append(clock[0])

    assert request_times[0] >= 60
    assert request_times[1] >= request_times[0] + 2
