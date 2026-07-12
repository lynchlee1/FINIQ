"""Small helpers for bounded concurrent task submission."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, Executor, Future, wait
from typing import TypeVar


T = TypeVar("T")
R = TypeVar("R")


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
