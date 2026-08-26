from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests

from finiq.data_scraper.core.client import download_disclosure_external_htmls
from finiq.data_scraper.core import kind_computers
from finiq.data_scraper.core.kind_computers import (
    KindVirtualComputer,
    allocate_computer_workers,
    build_kind_virtual_computers,
    create_kind_computer_session,
    kind_proxy_count_limit,
    kind_route_count_limit,
    normalize_kind_proxy_urls,
    check_kind_network_routes,
    run_kind_virtual_computers,
    split_items_round_robin,
)
from finiq.market_desk.web.features.disclosures.internal_html_download import (
    download_disclosure_internal_htmls,
)


class _PublicIpResponse:
    def __init__(self, public_ip: str) -> None:
        self.text = public_ip

    def raise_for_status(self) -> None:
        return None


class _PublicIpSession:
    def __init__(self, result: str | Exception) -> None:
        self._result = result

    def get(self, _url: str, *, timeout: float) -> _PublicIpResponse:
        assert timeout > 0
        if isinstance(self._result, Exception):
            raise self._result
        return _PublicIpResponse(self._result)

    def close(self) -> None:
        return None


def test_check_kind_network_routes_reports_unique_public_ips() -> None:
    public_ips = {
        None: "203.0.113.1",
        "http://127.0.0.1:25001": "203.0.113.2",
    }

    result = check_kind_network_routes(
        ["http://127.0.0.1:25001"],
        session_factory=lambda computer: _PublicIpSession(public_ips[computer.proxy_url]),
    )

    assert result["ready"] is True
    assert result["route_count"] == 2
    assert result["unique_ip_count"] == 2
    assert [route["status"] for route in result["routes"]] == ["ready", "ready"]
    assert all(route["unique"] is True for route in result["routes"])


def test_check_kind_network_routes_marks_duplicates_and_failures() -> None:
    results = {
        None: "203.0.113.1",
        "http://127.0.0.1:25001": "203.0.113.1",
        "http://127.0.0.1:25002": requests.ConnectionError("offline"),
    }

    result = check_kind_network_routes(
        ["http://127.0.0.1:25001", "http://127.0.0.1:25002"],
        session_factory=lambda computer: _PublicIpSession(results[computer.proxy_url]),
    )

    assert result["ready"] is False
    assert result["unique_ip_count"] == 1
    assert result["routes"][0]["unique"] is False
    assert result["routes"][1]["unique"] is False
    assert result["routes"][2]["status"] == "error"
    assert result["routes"][2]["public_ip"] is None


def test_split_items_round_robin_assigns_all_buckets() -> None:
    assert split_items_round_robin(["a", "b", "c", "d", "e"], 3) == [
        ["a", "d"],
        ["b", "e"],
        ["c"],
    ]


def test_allocate_computer_workers_preserves_total_limit() -> None:
    assert allocate_computer_workers(7, 5) == [2, 2, 1, 1, 1]
    assert allocate_computer_workers(5, 3) == [2, 2, 1]
    assert allocate_computer_workers(8, 8) == [1] * 8
    assert allocate_computer_workers(1, 1) == [1]


def test_normalize_kind_proxy_urls_accepts_cpu_limited_local_proxies() -> None:
    proxies = [
        f"http://127.0.0.1:{25001 + index}"
        for index in range(kind_proxy_count_limit())
    ]

    assert normalize_kind_proxy_urls(proxies) == proxies


@pytest.mark.parametrize(
    "value, message",
    [
        ("http://127.0.0.1:25001", "must be a list"),
        (["https://127.0.0.1:25001"], "must use http"),
        (["http://10.0.0.2:25001"], "must use localhost"),
        (["http://127.0.0.1"], "must include a port"),
        (["http://127.0.0.1:0"], "invalid port"),
        (
            ["http://127.0.0.1:25001", "http://localhost:25001"],
            "duplicate",
        ),
        (
            [
                f"http://127.0.0.1:{25001 + index}"
                for index in range(kind_proxy_count_limit() + 1)
            ],
            f"at most {kind_proxy_count_limit()}",
        ),
    ],
)
def test_normalize_kind_proxy_urls_rejects_invalid_values(
    value: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        normalize_kind_proxy_urls(value)


def test_build_kind_virtual_computers_uses_direct_plus_proxies() -> None:
    computers = build_kind_virtual_computers(
        ["http://127.0.0.1:25001", "http://127.0.0.1:25002"]
    )

    assert computers == [
        KindVirtualComputer(index=0, proxy_url=None),
        KindVirtualComputer(index=1, proxy_url="http://127.0.0.1:25001"),
        KindVirtualComputer(index=2, proxy_url="http://127.0.0.1:25002"),
    ]
    assert computers[0].label == "직접 연결"
    assert "직접 연결" in computers[0].describe(item_count=1, worker_count=1)
    assert "127.0.0.1:25001" in computers[1].describe(
        item_count=1, worker_count=1
    )


def test_build_kind_virtual_computers_supports_cpu_count_egresses() -> None:
    max_proxy_count = kind_proxy_count_limit()
    proxies = [
        f"http://127.0.0.1:{25001 + index}"
        for index in range(max_proxy_count)
    ]

    computers = build_kind_virtual_computers(proxies)

    assert len(computers) == kind_route_count_limit()
    assert computers[0] == KindVirtualComputer(index=0, proxy_url=None)
    if proxies:
        assert computers[-1] == KindVirtualComputer(
            index=max_proxy_count,
            proxy_url=proxies[-1],
        )


def test_kind_proxy_limit_uses_current_cpu_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(kind_computers, "available_cpu_count", lambda: 2)

    assert kind_route_count_limit() == 2
    assert kind_proxy_count_limit() == 1
    with pytest.raises(ValueError, match="at most 1 proxies"):
        normalize_kind_proxy_urls(
            ["http://127.0.0.1:25001", "http://127.0.0.1:25002"]
        )


def test_create_kind_computer_session_sets_only_explicit_proxy() -> None:
    direct = create_kind_computer_session(KindVirtualComputer(0, None), pool_size=2)
    proxied = create_kind_computer_session(
        KindVirtualComputer(1, "http://127.0.0.1:25001"), pool_size=2
    )
    try:
        assert direct.proxies == {}
        assert direct.trust_env is False
        assert proxied.proxies == {
            "http": "http://127.0.0.1:25001",
            "https": "http://127.0.0.1:25001",
        }
        assert proxied.trust_env is False
    finally:
        direct.close()
        proxied.close()


def test_run_kind_virtual_computers_uses_three_egress_threads() -> None:
    progress: list[str] = []
    results = run_kind_virtual_computers(
        items=["a", "b", "c", "d", "e", "f"],
        worker_qualname="finiq.data_scraper.core.kind_computers._identity_worker",
        worker_kwargs={},
        progress_callback=progress.append,
        proxy_urls=["http://127.0.0.1:25001", "http://127.0.0.1:25002"],
        max_workers=5,
    )

    assert results == [["a", "d"], ["b", "e"], ["c", "f"]]
    assert any(
        message.startswith("KIND 네트워크 경로 3개로") for message in progress
    )
    process_ids = {
        int(message.split(":")[1])
        for message in progress
        if message[:1].isdigit() and message.count(":") == 2
    }
    assert process_ids == {os.getpid()}


def test_external_html_dispatches_configured_egresses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(**kwargs: object) -> list[list[str]]:
        captured.update(kwargs)
        return [
            [str(tmp_path / "20250101000001.html")],
            [str(tmp_path / "20250101000002.html")],
            [str(tmp_path / "20250101000003.html")],
        ]

    monkeypatch.setattr(
        "finiq.data_scraper.core.client.run_kind_virtual_computers",
        fake_run,
    )
    saved = download_disclosure_external_htmls(
        output_directory=tmp_path,
        request_headers={},
        acpt_numbers=[
            "20250101000001",
            "20250101000002",
            "20250101000003",
        ],
        kind_proxy_urls=[
            "http://127.0.0.1:25001",
            "http://127.0.0.1:25002",
        ],
        max_workers=3,
        max_retries=0,
    )

    assert captured["proxy_urls"] == [
        "http://127.0.0.1:25001",
        "http://127.0.0.1:25002",
    ]
    assert [path.name for path in saved] == [
        "20250101000001.html",
        "20250101000002.html",
        "20250101000003.html",
    ]


def test_internal_html_dispatches_configured_egresses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(**kwargs: object) -> list[list[str]]:
        captured.update(kwargs)
        return [
            [str(tmp_path / "20250101000002.html")],
            [str(tmp_path / "20250101000001.html")],
        ]

    monkeypatch.setattr(
        "finiq.market_desk.web.features.disclosures.internal_html_download.run_kind_virtual_computers",
        fake_run,
    )
    saved = download_disclosure_internal_htmls(
        output_directory=tmp_path,
        request_headers={},
        targets=[
            {"acpt_no": "20250101000002", "doc_no": "2"},
            {"acpt_no": "20250101000001", "doc_no": "1"},
        ],
        kind_proxy_urls=["http://127.0.0.1:25001"],
        max_workers=2,
        skip_existing=False,
    )

    assert captured["proxy_urls"] == ["http://127.0.0.1:25001"]
    assert [path.stem for path in saved] == ["20250101000002", "20250101000001"]
