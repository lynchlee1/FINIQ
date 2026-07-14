from concurrent.futures import ThreadPoolExecutor

import pytest

import finiq.concurrency as concurrency
from finiq.concurrency import (
    available_cpu_count,
    bounded_as_completed,
    resolve_worker_count,
)


@pytest.mark.parametrize("detected", [None, 0, -1, True])
def test_available_cpu_count_falls_back_to_one(monkeypatch, detected) -> None:
    monkeypatch.setattr(concurrency.os, "cpu_count", lambda: detected)

    assert available_cpu_count() == 1


def test_available_cpu_count_falls_back_when_detection_fails(monkeypatch) -> None:
    def fail() -> int:
        raise OSError("cpu lookup failed")

    monkeypatch.setattr(concurrency.os, "cpu_count", fail)

    assert available_cpu_count() == 1


def test_resolve_worker_count_uses_cpu_and_task_limits(monkeypatch) -> None:
    monkeypatch.setattr(concurrency.os, "cpu_count", lambda: 12)

    assert resolve_worker_count() == 12
    assert resolve_worker_count(None, item_count=5) == 5
    assert resolve_worker_count(20, item_count=30) == 12
    assert resolve_worker_count(4, item_count=30) == 4


@pytest.mark.parametrize("value", [0, "many"])
def test_resolve_worker_count_rejects_invalid_explicit_values(value) -> None:
    with pytest.raises(ValueError):
        resolve_worker_count(value, field_name="parallel_workers")


def test_bounded_as_completed_does_not_consume_all_items_up_front() -> None:
    consumed: list[int] = []

    def items():
        for value in range(100):
            consumed.append(value)
            yield value

    with ThreadPoolExecutor(max_workers=2) as executor:
        completed = bounded_as_completed(
            executor,
            items(),
            lambda value: executor.submit(lambda item: item, value),
            max_pending=4,
        )
        first_future, first_item = next(completed)

        assert first_future.result() == first_item
        assert len(consumed) == 4

        remaining = [future.result() for future, _item in completed]

    assert len(remaining) == 99
    assert consumed == list(range(100))
