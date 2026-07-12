from concurrent.futures import ThreadPoolExecutor

from finiq.concurrency import bounded_as_completed


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
