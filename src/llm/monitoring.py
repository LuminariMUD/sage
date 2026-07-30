"""Performance monitoring for LLM requests."""

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def monitor_performance(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to monitor LLM request performance.

    Logs execution time and success/failure status for async functions.

    Args:
        func: Async function to monitor

    Returns:
        Wrapped function with performance monitoring

    Example:
        >>> @monitor_performance
        >>> async def generate_text(prompt: str) -> str:
        ...     # ... generation logic ...
        ...     return response
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        start_time = time.time()
        func_name = func.__name__

        try:
            result = await func(*args, **kwargs)
            elapsed = time.time() - start_time

            # Log performance
            logger.info(
                f"LLM request completed: {func_name}",
                extra={
                    "function": func_name,
                    "duration_ms": int(elapsed * 1000),
                    "duration_s": round(elapsed, 2),
                    "success": True,
                },
            )

            return result

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                f"LLM request failed: {func_name}",
                extra={
                    "function": func_name,
                    "duration_ms": int(elapsed * 1000),
                    "duration_s": round(elapsed, 2),
                    "error_type": type(e).__name__,
                },
            )
            raise

    return wrapper


def monitor_sync_performance(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to monitor synchronous function performance.

    Logs execution time and success/failure status for sync functions.

    Args:
        func: Synchronous function to monitor

    Returns:
        Wrapped function with performance monitoring

    Example:
        >>> @monitor_sync_performance
        >>> def process_data(data: list) -> dict:
        ...     # ... processing logic ...
        ...     return result
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        start_time = time.time()
        func_name = func.__name__

        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time

            # Log performance
            logger.info(
                f"Function completed: {func_name}",
                extra={
                    "function": func_name,
                    "duration_ms": int(elapsed * 1000),
                    "duration_s": round(elapsed, 2),
                    "success": True,
                },
            )

            return result

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                f"Function failed: {func_name}",
                extra={
                    "function": func_name,
                    "duration_ms": int(elapsed * 1000),
                    "duration_s": round(elapsed, 2),
                    "error_type": type(e).__name__,
                },
            )
            raise

    return wrapper


class PerformanceTracker:
    """Track performance metrics for LLM operations."""

    def __init__(self):
        """Initialize performance tracker."""
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_duration": 0.0,
            "min_duration": float("inf"),
            "max_duration": 0.0,
        }

    def record_request(self, duration: float, success: bool = True):
        """
        Record a request's performance metrics.

        Args:
            duration: Request duration in seconds
            success: Whether the request succeeded
        """
        self.metrics["total_requests"] += 1
        if success:
            self.metrics["successful_requests"] += 1
        else:
            self.metrics["failed_requests"] += 1

        self.metrics["total_duration"] += duration
        self.metrics["min_duration"] = min(self.metrics["min_duration"], duration)
        self.metrics["max_duration"] = max(self.metrics["max_duration"], duration)

    def get_stats(self) -> dict:
        """
        Get performance statistics.

        Returns:
            Dictionary with performance stats
        """
        total_requests = self.metrics["total_requests"]
        if total_requests == 0:
            return {
                "total_requests": 0,
                "avg_duration_ms": 0,
                "success_rate": 0.0,
            }

        avg_duration = self.metrics["total_duration"] / total_requests
        success_rate = self.metrics["successful_requests"] / total_requests

        return {
            "total_requests": total_requests,
            "successful_requests": self.metrics["successful_requests"],
            "failed_requests": self.metrics["failed_requests"],
            "avg_duration_ms": int(avg_duration * 1000),
            "min_duration_ms": int(self.metrics["min_duration"] * 1000),
            "max_duration_ms": int(self.metrics["max_duration"] * 1000),
            "success_rate": round(success_rate * 100, 2),
        }

    def reset(self):
        """Reset all metrics."""
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_duration": 0.0,
            "min_duration": float("inf"),
            "max_duration": 0.0,
        }


# Global performance tracker
_performance_tracker = PerformanceTracker()


def get_performance_stats() -> dict:
    """
    Get global performance statistics.

    Returns:
        Dictionary with performance stats
    """
    return _performance_tracker.get_stats()
