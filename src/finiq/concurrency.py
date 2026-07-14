"""Small helpers for bounded concurrent task submission."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, Executor, Future, wait
from typing import TypeVar


T = TypeVar("T")
R = TypeVar("R")


def available_cpu_count() -> int:
    """Return the process-wide worker default, falling back to one CPU."""
    try:
        count = os.cpu_count()
    except Exception:
        return 1
    if isinstance(count, bool) or not isinstance(count, int) or count < 1:
        return 1
    return count


def resolve_worker_count(
    value: object = None,
    *,
    item_count: int | None = None,
    field_name: str = "workers",
) -> int:
    """Resolve a worker value against the shared CPU and optional task limits."""
    cpu_limit = available_cpu_count()
    if value in (None, ""):
        requested = cpu_limit
    else:
        try:
            requested = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be an integer") from exc
        if requested < 1:
            raise ValueError(f"{field_name} must be >= 1")

    limits = [requested, cpu_limit]
    if item_count is not None:
        limits.append(max(1, item_count))
    return max(1, min(limits))


def bounded_as_completed(
    executor: Executor,
    items: Iterable[T],
    submit: Callable[[T], Future[R]],
    *,
    max_pending: int,
) -> Iterator[tuple[Future[R], T]]:
    """Yield completed futures while keeping only ``max_pending`` submitted."""
    if max_pending < 1:
        raise ValueError("max_pending must be >= 1")

    iterator = iter(items)
    pending: dict[Future[R], T] = {}

    def fill() -> None:
        while len(pending) < max_pending:
            try:
                item = next(iterator)
            except StopIteration:
                return
            pending[submit(item)] = item

    fill()
    while pending:
        completed, _ = wait(pending, return_when=FIRST_COMPLETED)
        for future in completed:
            item = pending.pop(future)
            yield future, item
        fill()
