"""Two isolated KIND clients so one machine can download at twice the per-computer limit."""

from __future__ import annotations

import importlib
import ipaddress
import os
import re
import socket
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from multiprocessing import get_context
from queue import Empty
from typing import Any, TypeVar

import requests
from requests.adapters import HTTPAdapter

KIND_VIRTUAL_COMPUTER_COUNT = 2
KIND_HOSTS = frozenset({"kind.krx.co.kr", "www.kind.krx.co.kr"})
KIND_VIRTUAL_COMPUTER_USER_AGENTS = (
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
)

T = TypeVar("T")
ProgressCallback = Callable[[str], None]
CancelCheck = Callable[[], bool]


@dataclass(frozen=True)
class KindVirtualComputer:
    index: int
    source_ip: str | None
    destination_ip: str | None
    user_agent: str

    @property
    def label(self) -> str:
        return f"가상 컴퓨터 {self.index + 1}"

    def describe(self, *, item_count: int, worker_count: int) -> str:
        parts = [f"{self.label}: 대상 {item_count}건", f"워커 {worker_count}개"]
        if self.source_ip and self.destination_ip:
            parts.append(f"{self.source_ip} → {self.destination_ip}")
        elif self.source_ip:
            parts.append(self.source_ip)
        elif self.destination_ip:
            parts.append(self.destination_ip)
        return " · ".join(parts)


class KindSourceAddressAdapter(HTTPAdapter):
    """Bind outgoing KIND sockets to one local address."""

    def __init__(self, source_ip: str, **kwargs: Any) -> None:
        self.source_ip = source_ip
        super().__init__(**kwargs)

    def init_poolmanager(
        self,
        connections: int,
        maxsize: int,
        block: bool = False,
        **pool_kwargs: Any,
    ) -> None:
        pool_kwargs["source_address"] = (self.source_ip, 0)
        return super().init_poolmanager(connections, maxsize, block, **pool_kwargs)

    def proxy_manager_for(self, proxy: str, **proxy_kwargs: Any) -> Any:
        proxy_kwargs["source_address"] = (self.source_ip, 0)
        return super().proxy_manager_for(proxy, **proxy_kwargs)


def list_local_ipv4_addresses() -> list[str]:
    """Return unique non-loopback IPv4 addresses on this machine."""
    found: list[str] = []
    seen: set[str] = set()

    def add(host: str) -> None:
        try:
            parsed = ipaddress.ip_address(host)
        except ValueError:
            return
        if parsed.version != 4 or parsed.is_loopback or parsed.is_link_local:
            return
        if parsed.is_multicast or parsed.is_unspecified:
            return
        if host not in seen:
            seen.add(host)
            found.append(host)

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("kind.krx.co.kr", 443))
            add(sock.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(
            socket.gethostname(), None, socket.AF_INET, socket.SOCK_STREAM
        ):
            add(info[4][0])
    except socket.gaierror:
        pass
    for command in (("ifconfig",), ("ip", "-4", "-o", "addr")):
        try:
            output = subprocess.check_output(
                command, text=True, stderr=subprocess.DEVNULL
            )
        except (FileNotFoundError, subprocess.CalledProcessError, OSError):
            continue
        for match in re.finditer(
            r"\b(?:inet\s+)?(\d{1,3}(?:\.\d{1,3}){3})(?:/\d+)?\b", output
        ):
            add(match.group(1))
        break
    return found


def list_kind_ipv4_addresses() -> list[str]:
    """Return unique IPv4 addresses currently published for KIND."""
    found: list[str] = []
    seen: set[str] = set()
    try:
        infos = socket.getaddrinfo("kind.krx.co.kr", 443, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror:
        return found
    for info in infos:
        host = info[4][0]
        if host not in seen:
            seen.add(host)
            found.append(host)
    return found


def build_kind_virtual_computers(
    count: int = KIND_VIRTUAL_COMPUTER_COUNT,
) -> list[KindVirtualComputer]:
    if count < 1:
        raise ValueError("virtual computer count must be >= 1")
    source_ips = list_local_ipv4_addresses()
    destination_ips = list_kind_ipv4_addresses()
    computers: list[KindVirtualComputer] = []
    for index in range(count):
        computers.append(
            KindVirtualComputer(
                index=index,
                source_ip=source_ips[index] if index < len(source_ips) else None,
                destination_ip=(
                    destination_ips[index] if index < len(destination_ips) else None
                ),
                user_agent=KIND_VIRTUAL_COMPUTER_USER_AGENTS[
                    index % len(KIND_VIRTUAL_COMPUTER_USER_AGENTS)
                ],
            )
        )
    return computers


def split_items_round_robin(items: Sequence[T], count: int) -> list[list[T]]:
    if count < 1:
        raise ValueError("virtual computer count must be >= 1")
    buckets: list[list[T]] = [[] for _ in range(count)]
    for index, item in enumerate(items):
        buckets[index % count].append(item)
    return buckets


def headers_for_computer(
    computer: KindVirtualComputer,
    request_headers: Mapping[str, object],
) -> dict[str, str]:
    headers = {str(key): str(value) for key, value in request_headers.items()}
    headers["User-Agent"] = computer.user_agent
    return headers


def create_kind_computer_session(
    computer: KindVirtualComputer | None,
    *,
    pool_size: int = 10,
) -> requests.Session:
    session = requests.Session()
    adapter_kwargs = {"pool_connections": pool_size, "pool_maxsize": pool_size}
    adapter: HTTPAdapter
    if computer is not None and computer.source_ip:
        adapter = KindSourceAddressAdapter(computer.source_ip, **adapter_kwargs)
    else:
        adapter = HTTPAdapter(**adapter_kwargs)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def session_uses_source_address(session: requests.Session) -> bool:
    adapters = getattr(session, "adapters", {})
    return any(
        isinstance(adapter, KindSourceAddressAdapter) for adapter in adapters.values()
    )


def prepare_kind_virtual_computer(computer: KindVirtualComputer) -> None:
    """Pin KIND host lookups to this computer's destination IP in the current process."""
    destination_ip = computer.destination_ip
    if not destination_ip:
        return
    real_getaddrinfo = socket.getaddrinfo

    def pinned_getaddrinfo(
        host: str | bytes | None,
        port: Any,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[Any, ...]]:
        hostname = host.decode() if isinstance(host, bytes) else host
        if hostname not in KIND_HOSTS:
            return real_getaddrinfo(host, port, family, type, proto, flags)
        port_number = 0 if port in (None, "") else int(port)
        socktype = type or socket.SOCK_STREAM
        protocol = proto or socket.IPPROTO_TCP
        return [
            (
                socket.AF_INET,
                socktype,
                protocol,
                "",
                (destination_ip, port_number),
            )
        ]

    socket.getaddrinfo = pinned_getaddrinfo  # type: ignore[assignment]


def workers_per_computer(max_workers: int, computer_count: int) -> int:
    if computer_count < 1:
        raise ValueError("virtual computer count must be >= 1")
    return max(1, (max_workers + computer_count - 1) // computer_count)


def resolve_virtual_computer_count(
    value: object,
    *,
    item_count: int,
    session: requests.Session | None,
) -> int:
    if value in (None, ""):
        count = 1
    else:
        try:
            count = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("virtual_computer_count must be an integer") from exc
    if count not in {1, 2}:
        raise ValueError("virtual_computer_count must be 1 or 2")
    if session is not None and count > 1:
        raise ValueError("session cannot be combined with virtual_computer_count > 1")
    if item_count < 2:
        return 1
    return count


def _computer_process_entry(
    worker_qualname: str,
    computer: KindVirtualComputer,
    items: list[Any],
    worker_kwargs: dict[str, Any],
    progress_queue: Any,
    cancel_event: Any,
    result_queue: Any,
) -> None:
    prepare_kind_virtual_computer(computer)
    module_name, func_name = worker_qualname.rsplit(".", 1)
    worker = getattr(importlib.import_module(module_name), func_name)
    try:
        result = worker(
            computer, items, worker_kwargs, progress_queue, cancel_event
        )
        result_queue.put(("ok", computer.index, result))
    except Exception as exc:
        result_queue.put(("err", computer.index, f"{type(exc).__name__}: {exc}"))


def _identity_worker(
    computer: KindVirtualComputer,
    items: list[Any],
    worker_kwargs: dict[str, Any],
    progress_queue: Any,
    cancel_event: Any,
) -> list[Any]:
    del worker_kwargs, cancel_event
    progress_queue.put(f"{computer.index}:{os.getpid()}")
    return list(items)


def run_kind_virtual_computers(
    *,
    items: Sequence[T],
    worker_qualname: str,
    worker_kwargs: dict[str, Any],
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    computer_count: int = KIND_VIRTUAL_COMPUTER_COUNT,
    max_workers: int = 1,
) -> list[list[Any]]:
    """Run ``worker_qualname`` on isolated processes and return per-computer results."""
    if computer_count not in {1, 2}:
        raise ValueError("virtual_computer_count must be 1 or 2")
    computers = build_kind_virtual_computers(computer_count)
    buckets = split_items_round_robin(items, computer_count)
    assigned = [
        (computer, bucket)
        for computer, bucket in zip(computers, buckets, strict=True)
        if bucket
    ]
    per_computer_workers = workers_per_computer(max_workers, max(1, len(assigned)))
    if progress_callback is not None:
        progress_callback(f"가상 컴퓨터 {len(assigned)}대로 KIND 저장을 시작합니다.")
        for computer, bucket in assigned:
            progress_callback(
                computer.describe(
                    item_count=len(bucket), worker_count=per_computer_workers
                )
            )

    child_kwargs = dict(worker_kwargs)
    child_kwargs["max_workers"] = per_computer_workers

    if len(assigned) == 1:
        computer, bucket = assigned[0]

        class _LocalQueue:
            def put(self, message: str) -> None:
                if progress_callback is not None:
                    progress_callback(message)

        class _LocalEvent:
            def is_set(self) -> bool:
                return bool(cancel_check is not None and cancel_check())

        module_name, func_name = worker_qualname.rsplit(".", 1)
        worker = getattr(importlib.import_module(module_name), func_name)
        result = worker(computer, bucket, child_kwargs, _LocalQueue(), _LocalEvent())
        results: list[list[Any]] = [[] for _ in computers]
        results[computer.index] = result
        return results

    context = get_context("spawn")
    progress_queue = context.Queue()
    result_queue = context.Queue()
    cancel_event = context.Event()
    processes = [
        context.Process(
            target=_computer_process_entry,
            args=(
                worker_qualname,
                computer,
                bucket,
                child_kwargs,
                progress_queue,
                cancel_event,
                result_queue,
            ),
        )
        for computer, bucket in assigned
    ]
    collected: dict[int, list[Any]] = {}
    errors: list[str] = []

    def drain_progress() -> None:
        while True:
            try:
                message = progress_queue.get_nowait()
            except Empty:
                return
            if progress_callback is not None:
                progress_callback(str(message))

    def drain_results() -> None:
        while True:
            try:
                status, index, payload = result_queue.get_nowait()
            except Empty:
                return
            if status == "ok":
                collected[int(index)] = list(payload)
            else:
                errors.append(str(payload))

    try:
        for process in processes:
            process.start()
        while len(collected) + len(errors) < len(processes):
            if cancel_check is not None and cancel_check():
                cancel_event.set()
            drain_progress()
            try:
                status, index, payload = result_queue.get(timeout=0.1)
            except Empty:
                if not any(process.is_alive() for process in processes):
                    drain_progress()
                    drain_results()
                    break
                continue
            if status == "ok":
                collected[int(index)] = list(payload)
            else:
                errors.append(str(payload))
        drain_progress()
        drain_results()
        crashed = [
            computer.label
            for computer, _bucket in assigned
            if computer.index not in collected
        ]
        if crashed and not errors:
            errors.append("프로세스 종료: " + ", ".join(crashed))
        if errors:
            raise RuntimeError(
                "가상 컴퓨터 KIND 저장이 실패했습니다: " + "; ".join(errors)
            )
    finally:
        cancel_event.set()
        for process in processes:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=2)

    return [collected.get(computer.index, []) for computer in computers]


__all__ = [
    "KIND_VIRTUAL_COMPUTER_COUNT",
    "KindSourceAddressAdapter",
    "KindVirtualComputer",
    "build_kind_virtual_computers",
    "create_kind_computer_session",
    "headers_for_computer",
    "list_kind_ipv4_addresses",
    "list_local_ipv4_addresses",
    "prepare_kind_virtual_computer",
    "resolve_virtual_computer_count",
    "run_kind_virtual_computers",
    "session_uses_source_address",
    "split_items_round_robin",
    "workers_per_computer",
]
