"""Role-aware Docker health check for API and graph-worker containers."""

from __future__ import annotations

import os
import sys
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from src.graphiti.heartbeat import (
    heartbeat_is_fresh,
    heartbeat_max_age,
    heartbeat_path,
)

API_ROLE = "api"
GRAPH_WORKER_ROLE = "graph-worker"
GRAPH_WATCHDOG_ROLE = "graph-watchdog"
GRAPH_FINALIZER_ROLE = "graph-finalizer"
HEARTBEAT_ROLES = {GRAPH_WORKER_ROLE, GRAPH_WATCHDOG_ROLE, GRAPH_FINALIZER_ROLE}
DEFAULT_API_PORT = 8003
API_HEALTH_TIMEOUT_SECONDS = 5


def healthcheck_status(
    environment: Mapping[str, str] | None = None,
    opener: Callable[..., Any] | None = None,
) -> int:
    """Return a Docker-compatible status without applying an API probe to workers."""
    values = os.environ if environment is None else environment
    role = values.get("SAGE_CONTAINER_ROLE", API_ROLE).strip().lower()
    if role in HEARTBEAT_ROLES:
        try:
            path = heartbeat_path(values)
            maximum_age = heartbeat_max_age(values)
        except ValueError:
            print("Container health check failed: invalid heartbeat configuration", file=sys.stderr)
            return 1
        if not heartbeat_is_fresh(path, max_age_seconds=maximum_age):
            print("Container health check failed: heartbeat is missing or stale", file=sys.stderr)
            return 1
        return 0
    if role != API_ROLE:
        print("Container health check failed: unsupported container role", file=sys.stderr)
        return 1

    raw_port = values.get("API_PORT", str(DEFAULT_API_PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError:
        print("Container health check failed: invalid API port", file=sys.stderr)
        return 1
    if not 1 <= port <= 65_535:
        print("Container health check failed: invalid API port", file=sys.stderr)
        return 1

    open_url = urllib.request.urlopen if opener is None else opener
    try:
        with open_url(
            f"http://127.0.0.1:{port}/api/v1/health",
            timeout=API_HEALTH_TIMEOUT_SECONDS,
        ) as response:
            response.read(1)
    except (OSError, ValueError):
        print("Container health check failed: API probe unsuccessful", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(healthcheck_status())
