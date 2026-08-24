from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest

from finiq.data_scraper.core.client import download_disclosure_external_htmls
from finiq.data_scraper.core.kind_computers import (
    KIND_VIRTUAL_COMPUTER_COUNT,
    KindSourceAddressAdapter,
    KindVirtualComputer,
    build_kind_virtual_computers,
    create_kind_computer_session,
    headers_for_computer,
    prepare_kind_virtual_computer,
    resolve_virtual_computer_count,
    run_kind_virtual_computers,
    session_uses_source_address,
    split_items_round_robin,
    workers_per_computer,
)
from finiq.market_desk.web.features.disclosures.internal_html_download import (
    download_disclosure_internal_htmls,
)


def test_split_items_round_robin_assigns_even_and_odd() -> None:
    assert split_items_round_robin(["a", "b", "c", "d", "e"], 2) == [
        ["a", "c", "e"],
        ["b", "d"],
    ]


def test_workers_per_computer_splits_total() -> None:
    assert workers_per_computer(8, 2) == 4
    assert workers_per_computer(1, 2) == 1


def test_resolve_virtual_computer_count_keeps_one_item_on_one_computer() -> None:
    assert (
        resolve_virtual_computer_count(2, item_count=1, session=None) == 1
    )
    assert (
        resolve_virtual_computer_count(2, item_count=2, session=None) == 2
    )


def test_resolve_virtual_computer_count_rejects_session_plus_two() -> None:
    with pytest.raises(ValueError, match="session cannot be combined"):
        resolve_virtual_computer_count(2, item_count=4, session=object())  # type: ignore[arg-type]


def test_build_kind_virtual_computers_separates_ips_and_user_agents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "finiq.data_scraper.core.kind_computers.list_local_ipv4_addresses",
        lambda: ["192.168.0.10", "192.168.0.11"],
    )
    monkeypatch.setattr(
        "finiq.data_scraper.core.kind_computers.list_kind_ipv4_addresses",
        lambda: ["23.53.2.185", "23.53.2.131"],
    )

    computers = build_kind_virtual_computers(2)

    assert computers[0].source_ip == "192.168.0.10"
    assert computers[1].source_ip == "192.168.0.11"
    assert computers[0].destination_ip == "23.53.2.185"
    assert computers[1].destination_ip == "23.53.2.131"
    assert computers[0].user_agent != computers[1].user_agent
    assert computers[0].label == "가상 컴퓨터 1"


def test_source_address_adapter_binds_local_ip() -> None:
    adapter = KindSourceAddressAdapter("192.168.0.10", pool_connections=1, pool_maxsize=1)
    adapter.init_poolmanager(1, 1)

    assert adapter.poolmanager.connection_pool_kw["source_address"] == (
        "192.168.0.10",
        0,
    )
    session = create_kind_computer_session(
        KindVirtualComputer(
            index=0,
            source_ip="192.168.0.10",
            destination_ip="23.53.2.185",
            user_agent="test-agent",
        ),
        pool_size=2,
    )
    assert session_uses_source_address(session)
    assert headers_for_computer(
        KindVirtualComputer(0, None, None, "test-agent"),
        {"Accept": "text/html"},
    )["User-Agent"] == "test-agent"
    session.close()


def test_prepare_kind_virtual_computer_pins_kind_host_only() -> None:
    original = socket.getaddrinfo
    computer = KindVirtualComputer(
        index=0,
        source_ip=None,
        destination_ip="203.0.113.10",
        user_agent="test-agent",
    )
    try:
        prepare_kind_virtual_computer(computer)
        kind_infos = socket.getaddrinfo("kind.krx.co.kr", 443)
        assert kind_infos[0][4][0] == "203.0.113.10"
        other_infos = socket.getaddrinfo(
            "127.0.0.1", 443, socket.AF_INET, socket.SOCK_STREAM
        )
        assert other_infos[0][4][0] == "127.0.0.1"
    finally:
        socket.getaddrinfo = original


def test_run_kind_virtual_computers_uses_two_processes() -> None:
    progress: list[str] = []
    results = run_kind_virtual_computers(
        items=["a", "b"],
        worker_qualname="finiq.data_scraper.core.kind_computers._identity_worker",
        worker_kwargs={},
        progress_callback=progress.append,
        computer_count=2,
        max_workers=2,
    )

    assert results[0] == ["a"]
    assert results[1] == ["b"]
    assert any(message.startswith("가상 컴퓨터 2대로") for message in progress)
    pids = {
        int(message.split(":")[1])
        for message in progress
        if message[:1].isdigit() and ":" in message
    }
    assert len(pids) == 2
    assert os.getpid() not in pids


def test_external_html_dispatches_two_virtual_computers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(**kwargs: object) -> list[list[str]]:
        captured.update(kwargs)
        return [[str(tmp_path / "20250101000001.html")], [str(tmp_path / "20250101000002.html")]]

    monkeypatch.setattr(
        "finiq.data_scraper.core.client.run_kind_virtual_computers",
        fake_run,
    )
    saved = download_disclosure_external_htmls(
        output_directory=tmp_path,
        request_headers={},
        acpt_numbers=["20250101000001", "20250101000002"],
        virtual_computer_count=KIND_VIRTUAL_COMPUTER_COUNT,
        max_retries=0,
    )

    assert captured["computer_count"] == 2
    assert captured["items"] == ["20250101000001", "20250101000002"]
    assert [path.name for path in saved] == [
        "20250101000001.html",
        "20250101000002.html",
    ]


def test_internal_html_dispatches_two_virtual_computers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(**kwargs: object) -> list[list[str]]:
        captured.update(kwargs)
        return [[str(tmp_path / "20250101000002.html")], [str(tmp_path / "20250101000001.html")]]

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
        virtual_computer_count=2,
        skip_existing=False,
    )

    assert captured["computer_count"] == 2
    assert [path.stem for path in saved] == ["20250101000002", "20250101000001"]
