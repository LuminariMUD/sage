"""Request queue for Ollama to prevent concurrent overload."""

import asyncio
import logging
import threading
import weakref
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


class OllamaRequestQueue:
    """Queue to serialize Ollama requests and prevent OOM."""

    def __init__(self, max_concurrent: int = 1):
        """
        Initialize queue.

        Args:
            max_concurrent: Maximum number of concurrent requests (default: 1)
        """
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.request_count = 0
        self._lock = asyncio.Lock()

    async def execute[T](
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute request with queue management.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func
        """
        async with self.semaphore:
            async with self._lock:
                self.request_count += 1
                current_count = self.request_count

            logger.debug(f"Executing Ollama request #{current_count}")

            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                logger.error(
                    "Ollama request #%s failed (%s)",
                    current_count,
                    type(e).__name__,
                )
                raise
            finally:
                async with self._lock:
                    self.request_count -= 1


_MAX_CONCURRENT_REQUESTS = 1
_request_queues: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, OllamaRequestQueue] = (
    weakref.WeakKeyDictionary()
)
_request_queues_lock = threading.Lock()


def _queue_for_loop(loop: asyncio.AbstractEventLoop) -> OllamaRequestQueue:
    """Return a queue whose asyncio primitives belong to ``loop``."""
    with _request_queues_lock:
        queue = _request_queues.get(loop)
        if queue is None:
            queue = OllamaRequestQueue(max_concurrent=_MAX_CONCURRENT_REQUESTS)
            _request_queues[loop] = queue
        return queue


async def queued_ollama_request[T](
    func: Callable[..., Awaitable[T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    """
    Execute Ollama request through queue.

    This function ensures that Ollama requests are serialized to prevent
    out-of-memory errors on systems with limited VRAM.

    Args:
        func: Async function to execute
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result from func

    Example:
        >>> async def generate_text(prompt: str) -> str:
        ...     # ... generation logic ...
        ...     return response
        >>>
        >>> result = await queued_ollama_request(generate_text, "Hello world")
    """
    queue = _queue_for_loop(asyncio.get_running_loop())
    return await queue.execute(func, *args, **kwargs)


def get_queue_status() -> dict:
    """
    Get current queue status.

    Returns:
        Dictionary with queue statistics
    """
    try:
        queue = _queue_for_loop(asyncio.get_running_loop())
    except RuntimeError:
        return {"active_requests": 0, "max_concurrent": _MAX_CONCURRENT_REQUESTS}
    return {
        "active_requests": queue.request_count,
        "max_concurrent": queue.max_concurrent,
    }
