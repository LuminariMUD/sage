"""Request queue for Ollama to prevent concurrent overload."""

import asyncio
import logging
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class OllamaRequestQueue:
    """Queue to serialize Ollama requests and prevent OOM."""

    def __init__(self, max_concurrent: int = 1):
        """
        Initialize queue.

        Args:
            max_concurrent: Maximum number of concurrent requests (default: 1)
        """
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.request_count = 0
        self._lock = asyncio.Lock()

    async def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
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


# Global queue instance
_request_queue = OllamaRequestQueue(max_concurrent=1)


async def queued_ollama_request(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
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
    return await _request_queue.execute(func, *args, **kwargs)


def get_queue_status() -> dict:
    """
    Get current queue status.

    Returns:
        Dictionary with queue statistics
    """
    return {
        "active_requests": _request_queue.request_count,
        "max_concurrent": _request_queue.semaphore._value,
    }
