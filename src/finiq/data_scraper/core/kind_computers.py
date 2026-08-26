"""Explicit KIND egress sessions for direct and local HTTP proxy connections."""

from __future__ import annotations

import importlib
import ipaddress
import os
import threading
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, TypeVar
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter

from finiq.concurrency import available_cpu_count


PUBLIC_IP_CHECK_URL = "https://api.ipify.org"

T = TypeVar("T")
ProgressCallback = Callable[[str], None]
CancelCheck = Callable[[], bool]


@dataclass(frozen=True)
class KindVirtualComputer:
    index: int
    proxy_url: str | None

    @property
    def label(self) -> str:
        return "직접 연결" if self.proxy_url is None else f"경로 {self.index}"

    def describe(self, *, item_count: int, worker_count: int) -> str:
        proxy = f" · {self.proxy_url}" if self.proxy_url else ""
        return f"{self.label}: 대상 {item_count}건 · 워커 {worker_count}개{proxy}"


def kind_route_count_limit() -> int:
    return available_cpu_count()


def kind_proxy_count_limit() -> int:
    return kind_route_count_limit() - 1


def normalize_kind_proxy_urls(value: object) -> list[str]:
    """Validate loopback HTTP CONNECT proxy URLs against the CPU limit."""
    if value in (None, ""):
        return []
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError("kind_proxy_urls must be a list")
    max_proxy_count = kind_proxy_count_limit()
    if len(value) > max_proxy_count:
        raise ValueError(
            f"kind_proxy_urls must contain at most {max_proxy_count} proxies"
        )

    normalized: list[str] = []
    seen_endpoints: set[tuple[str, int]] = set()
    for index, raw_url in enumerate(value):
        proxy_url = str(raw_url or "").strip()
        parsed = urlsplit(proxy_url)
        if parsed.scheme != "http":
            raise ValueError(f"kind_proxy_urls[{index}] must use http")
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError(f"kind_proxy_urls[{index}] must use localhost")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError(
                f"kind_proxy_urls[{index}] has an invalid port"
            ) from exc
        if port is None:
            raise ValueError(f"kind_proxy_urls[{index}] must include a port")
        if port == 0:
            raise ValueError(f"kind_proxy_urls[{index}] has an invalid port")
        if parsed.username or parsed.password:
            raise ValueError(
                f"kind_proxy_urls[{index}] must not include credentials"
            )
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError(
                f"kind_proxy_urls[{index}] must not include a path, query, or fragment"
            )
        endpoint = ("127.0.0.1", port)
        if endpoint in seen_endpoints:
            raise ValueError("kind_proxy_urls contains a duplicate proxy")
        seen_endpoints.add(endpoint)
        normalized.append(proxy_url.rstrip("/"))
    return normalized


def build_kind_virtual_computers(
    proxy_urls: Sequence[str] | None = None,
) -> list[KindVirtualComputer]:
    normalized_proxy_urls = normalize_kind_proxy_urls(proxy_urls)
    return [
        KindVirtualComputer(index=index, proxy_url=proxy_url)
        for index, proxy_url in enumerate([None, *normalized_proxy_urls])
    ]


def split_items_round_robin(items: Sequence[T], count: int) -> list[list[T]]:
    if count < 1:
        raise ValueError("route count must be >= 1")
    buckets: list[list[T]] = [[] for _ in range(count)]
    for index, item in enumerate(items):
        buckets[index % count].append(item)
    return buckets


def allocate_computer_workers(max_workers: int, computer_count: int) -> list[int]:
    if max_workers < 1:
        raise ValueError("max_workers must be >= 1")
    if computer_count < 1 or computer_count > max_workers:
        raise ValueError("computer_count must be between 1 and max_workers")
    base, remainder = divmod(max_workers, computer_count)
    return [base + (1 if index < remainder else 0) for index in range(computer_count)]


def create_kind_computer_session(
    computer: KindVirtualComputer,
    *,
    pool_size: int = 10,
) -> requests.Session:
    session = requests.Session()
    session.trust_env = False
    adapter = HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    if computer.proxy_url:
        session.proxies.update(
            {"http": computer.proxy_url, "https": computer.proxy_url}
        )
    return session


def check_kind_network_routes(
    proxy_urls: Sequence[str] | None = None,
    *,
    timeout: float = 10,
    session_factory: Callable[[KindVirtualComputer], requests.Session] = create_kind_computer_session,
) -> dict[str, Any]:
    """Check each configured egress and report whether its public IP is unique."""
    computers = build_kind_virtual_computers(proxy_urls)

    def check_one(computer: KindVirtualComputer) -> dict[str, Any]:
        session = session_factory(computer)
        try:
            response = session.get(PUBLIC_IP_CHECK_URL, timeout=timeout)
            response.raise_for_status()
            public_ip = str(ipaddress.ip_address(response.text.strip()))
            return {
                "index": computer.index,
                "label": "직접 연결" if computer.proxy_url is None else f"경로 {computer.index}",
                "proxy_url": computer.proxy_url,
                "status": "ready",
                "public_ip": public_ip,
                "unique": None,
            }
        except (requests.RequestException, ValueError):
            return {
                "index": computer.index,
                "label": "직접 연결" if computer.proxy_url is None else f"경로 {computer.index}",
                "proxy_url": computer.proxy_url,
                "status": "error",
                "public_ip": None,
                "unique": None,
            }
        finally:
            session.close()

    with ThreadPoolExecutor(
        max_workers=len(computers),
        thread_name_prefix="kind-route-check",
    ) as executor:
        routes = list(executor.map(check_one, computers))

    ip_counts = Counter(
        route["public_ip"] for route in routes if route["public_ip"] is not None
    )
    for route in routes:
        public_ip = route["public_ip"]
        if public_ip is not None:
            route["unique"] = ip_counts[public_ip] == 1

    return {
        "ready": all(
            route["status"] == "ready" and route["unique"] is True
            for route in routes
        ),
        "route_count": len(routes),
        "unique_ip_count": len(ip_counts),
        "routes": routes,
    }


class _ProgressQueue:
    def __init__(
        self,
        callback: ProgressCallback | None,
        lock: threading.Lock,
    ) -> None:
        self._callback = callback
        self._lock = lock

    def put(self, message: str) -> None:
        if self._callback is not None:
            with self._lock:
                self._callback(message)


class _CancelEvent:
    def __init__(self, cancel_check: CancelCheck | None) -> None:
        self._cancel_check = cancel_check
        self._cancelled = threading.Event()

    def is_set(self) -> bool:
        return self._cancelled.is_set() or bool(
            self._cancel_check is not None and self._cancel_check()
        )

    def set(self) -> None:
        self._cancelled.set()


def _identity_worker(
    computer: KindVirtualComputer,
    items: list[Any],
    worker_kwargs: dict[str, Any],
    progress_queue: Any,
    cancel_event: Any,
) -> list[Any]:
    del worker_kwargs, cancel_event
    progress_queue.put(f"{computer.index}:{os.getpid()}:{threading.get_ident()}")
    return list(items)


def run_kind_virtual_computers(
    *,
    items: Sequence[T],
    worker_qualname: str,
    worker_kwargs: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    proxy_urls: Sequence[str] | None = None,
    max_workers: int = 1,
) -> list[list[Any]]:
    """Run one isolated worker group for each explicit KIND egress."""
    if max_workers < 1:
        raise ValueError("max_workers must be >= 1")
    if not items:
        return []

    all_computers = build_kind_virtual_computers(proxy_urls)
    active_count = min(len(all_computers), len(items), max_workers)
    computers = all_computers[:active_count]
    buckets = split_items_round_robin(items, active_count)
    worker_counts = allocate_computer_workers(max_workers, active_count)

    if progress_callback is not None:
        progress_callback(f"KIND 네트워크 경로 {active_count}개로 저장을 시작합니다.")
        for computer, bucket, worker_count in zip(
            computers, buckets, worker_counts, strict=True
        ):
            progress_callback(
                computer.describe(
                    item_count=len(bucket), worker_count=worker_count
                )
            )

    module_name, func_name = worker_qualname.rsplit(".", 1)
    worker = getattr(importlib.import_module(module_name), func_name)
    progress_lock = threading.Lock()
    progress_queue = _ProgressQueue(progress_callback, progress_lock)
    cancel_event = _CancelEvent(cancel_check)
    collected: dict[int, list[Any]] = {}
    errors: list[str] = []

    def run_one(
        computer: KindVirtualComputer,
        bucket: list[T],
        worker_count: int,
    ) -> tuple[int, list[Any]]:
        computer_kwargs = dict(worker_kwargs)
        computer_kwargs["max_workers"] = worker_count
        result = worker(
            computer,
            bucket,
            computer_kwargs,
            progress_queue,
            cancel_event,
        )
        return computer.index, list(result)

    with ThreadPoolExecutor(
        max_workers=active_count,
        thread_name_prefix="kind-egress",
    ) as executor:
        future_computers = {
            executor.submit(run_one, computer, bucket, worker_count): computer
            for computer, bucket, worker_count in zip(
                computers, buckets, worker_counts, strict=True
            )
        }
        for future in as_completed(future_computers):
            computer = future_computers[future]
            try:
                index, result = future.result()
                collected[index] = result
            except Exception as exc:
                cancel_event.set()
                errors.append(f"{computer.label}: {type(exc).__name__}: {exc}")

    if errors:
        raise RuntimeError(
            "KIND 네트워크 경로 저장이 실패했습니다: " + "; ".join(errors)
        )
    return [collected[computer.index] for computer in computers]


__all__ = [
    "KindVirtualComputer",
    "allocate_computer_workers",
    "build_kind_virtual_computers",
    "create_kind_computer_session",
    "check_kind_network_routes",
    "kind_proxy_count_limit",
    "kind_route_count_limit",
    "normalize_kind_proxy_urls",
    "run_kind_virtual_computers",
    "split_items_round_robin",
]
