"""Start and stop FINIQ's local wireproxy launch agents."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence

from finiq.data_scraper.core.kind_computers import normalize_kind_proxy_urls


LAUNCH_AGENT_LABEL_PREFIX = "com.finiq.wireproxy.route"


def wireproxy_launch_agent_labels(
    proxy_urls: Sequence[str] | None,
) -> tuple[str, ...]:
    normalized_proxy_urls = normalize_kind_proxy_urls(proxy_urls)
    return tuple(
        f"{LAUNCH_AGENT_LABEL_PREFIX}{index}"
        for index in range(1, len(normalized_proxy_urls) + 1)
    )


def start_wireproxy_launch_agents(
    proxy_urls: Sequence[str] | None,
) -> tuple[str, ...]:
    labels = wireproxy_launch_agent_labels(proxy_urls)
    domain = f"gui/{os.getuid()}"
    for label in labels:
        subprocess.run(
            ["launchctl", "kickstart", "-k", f"{domain}/{label}"],
            check=True,
        )
    return labels


def stop_wireproxy_launch_agents(labels: Sequence[str]) -> None:
    domain = f"gui/{os.getuid()}"
    for label in reversed(labels):
        subprocess.run(
            ["launchctl", "kill", "SIGTERM", f"{domain}/{label}"],
            check=False,
        )
