from __future__ import annotations

import subprocess

from fastapi.testclient import TestClient

import finiq.market_desk.web.app as web_app
from finiq.market_desk.web import wireproxy_lifecycle


def test_wireproxy_launch_agents_follow_configured_proxy_count(monkeypatch) -> None:
    calls: list[tuple[list[str], bool]] = []

    def fake_run(command: list[str], *, check: bool) -> subprocess.CompletedProcess:
        calls.append((command, check))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(wireproxy_lifecycle.os, "getuid", lambda: 501)
    monkeypatch.setattr(wireproxy_lifecycle.subprocess, "run", fake_run)
    proxy_urls = [
        "http://127.0.0.1:25001",
        "http://127.0.0.1:25002",
    ]

    labels = wireproxy_lifecycle.start_wireproxy_launch_agents(proxy_urls)
    wireproxy_lifecycle.stop_wireproxy_launch_agents(labels)

    assert labels == (
        "com.finiq.wireproxy.route1",
        "com.finiq.wireproxy.route2",
    )
    assert calls == [
        (
            [
                "launchctl",
                "kickstart",
                "-k",
                "gui/501/com.finiq.wireproxy.route1",
            ],
            True,
        ),
        (
            [
                "launchctl",
                "kickstart",
                "-k",
                "gui/501/com.finiq.wireproxy.route2",
            ],
            True,
        ),
        (
            [
                "launchctl",
                "kill",
                "SIGTERM",
                "gui/501/com.finiq.wireproxy.route2",
            ],
            False,
        ),
        (
            [
                "launchctl",
                "kill",
                "SIGTERM",
                "gui/501/com.finiq.wireproxy.route1",
            ],
            False,
        ),
    ]


def test_market_desk_lifespan_starts_and_stops_wireproxy(monkeypatch) -> None:
    events: list[tuple[str, object]] = []

    def fake_start(proxy_urls: object) -> tuple[str, ...]:
        events.append(("start", list(proxy_urls)))
        return ("com.finiq.wireproxy.route1",)

    def fake_stop(labels: object) -> None:
        events.append(("stop", tuple(labels)))

    monkeypatch.setattr(web_app, "start_wireproxy_launch_agents", fake_start)
    monkeypatch.setattr(web_app, "stop_wireproxy_launch_agents", fake_stop)

    with TestClient(web_app.app):
        assert events == [("start", list(web_app.config.kind_proxy_urls))]

    assert events == [
        ("start", list(web_app.config.kind_proxy_urls)),
        ("stop", ("com.finiq.wireproxy.route1",)),
    ]
