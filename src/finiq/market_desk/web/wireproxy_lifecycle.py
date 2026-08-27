"""Start and stop FINIQ's local wireproxy launch agents."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from urllib.parse import urlsplit

from finiq.data_scraper.core.kind_computers import normalize_kind_proxy_urls


LAUNCH_AGENT_LABEL_PREFIX = "com.finiq.wireproxy.route"
WIREPROXY_PORT_BASE = 25000
WIREPROXY_ROUTE_COUNT = 7


def wireproxy_launch_agent_labels(
    proxy_urls: Sequence[str] | None,
) -> tuple[str, ...]:
    normalized_proxy_urls = normalize_kind_proxy_urls(proxy_urls)
    labels: list[str] = []
    for proxy_url in normalized_proxy_urls:
        port = urlsplit(proxy_url).port
        route_number = int(port or 0) - WIREPROXY_PORT_BASE
        if route_number < 1 or route_number > WIREPROXY_ROUTE_COUNT:
            continue
        labels.append(f"{LAUNCH_AGENT_LABEL_PREFIX}{route_number}")
    return tuple(labels)


def start_wireproxy_launch_agents(
    proxy_urls: Sequence[str] | None,
) -> tuple[str, ...]:
    labels = wireproxy_launch_agent_labels(proxy_urls)
    domain = f"gui/{os.getuid()}"
    started_labels: list[str] = []
    try:
        for label in labels:
            subprocess.run(
                ["launchctl", "kickstart", "-k", f"{domain}/{label}"],
                check=True,
            )
            started_labels.append(label)
    except Exception:
        stop_wireproxy_launch_agents(started_labels)
        raise
    return labels


def stop_wireproxy_launch_agents(labels: Sequence[str]) -> None:
    domain = f"gui/{os.getuid()}"
    for label in reversed(labels):
        subprocess.run(
            ["launchctl", "kill", "SIGTERM", f"{domain}/{label}"],
            check=False,
        )
