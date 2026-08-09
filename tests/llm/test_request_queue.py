"""Regression tests for the event-loop-local Ollama request queue."""

import asyncio

from src.llm.request_queue import get_queue_status, queued_ollama_request


def test_queue_can_be_reused_across_event_loops() -> None:
    """Sequential ``asyncio.run`` calls must not share bound primitives."""

    async def exercise_queue() -> list[int]:
        async def double(value: int) -> int:
            await asyncio.sleep(0)
            return value * 2

        return await asyncio.gather(*(queued_ollama_request(double, value) for value in range(4)))

    assert asyncio.run(exercise_queue()) == [0, 2, 4, 6]
    assert asyncio.run(exercise_queue()) == [0, 2, 4, 6]


def test_queue_serializes_requests() -> None:
    """Only the configured number of requests may execute concurrently."""

    async def exercise_queue() -> tuple[int, dict[str, int]]:
        active = 0
        peak_active = 0

        async def observe_concurrency() -> None:
            nonlocal active, peak_active
            active += 1
            peak_active = max(peak_active, active)
            await asyncio.sleep(0.01)
            active -= 1

        await asyncio.gather(*(queued_ollama_request(observe_concurrency) for _ in range(5)))
        return peak_active, get_queue_status()

    peak_active, status = asyncio.run(exercise_queue())

    assert peak_active == 1
    assert status == {"active_requests": 0, "max_concurrent": 1}


def test_queue_status_is_available_without_a_running_loop() -> None:
    assert get_queue_status() == {"active_requests": 0, "max_concurrent": 1}
