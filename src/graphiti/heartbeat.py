"""Small filesystem heartbeat contract for non-HTTP graph services."""

from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path

DEFAULT_HEARTBEAT_MAX_AGE_SECONDS = 120


def heartbeat_path(environment: Mapping[str, str]) -> Path:
    """Resolve an explicit absolute heartbeat path."""
    raw_path = environment.get("SAGE_HEARTBEAT_FILE", "").strip()
    if not raw_path:
        raise ValueError("SAGE_HEARTBEAT_FILE is required for non-HTTP services")
    path = Path(raw_path)
    if not path.is_absolute():
        raise ValueError("SAGE_HEARTBEAT_FILE must be absolute")
    return path


def heartbeat_max_age(environment: Mapping[str, str]) -> int:
    """Resolve a bounded heartbeat freshness interval."""
    raw_value = environment.get(
        "SAGE_HEARTBEAT_MAX_AGE_SECONDS",
        str(DEFAULT_HEARTBEAT_MAX_AGE_SECONDS),
    ).strip()
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError("SAGE_HEARTBEAT_MAX_AGE_SECONDS must be an integer") from error
    if not 10 <= value <= 3600:
        raise ValueError("SAGE_HEARTBEAT_MAX_AGE_SECONDS must be between 10 and 3600")
    return value


def touch_heartbeat(path: Path) -> None:
    """Create or refresh one service-owned liveness marker."""
    path.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    path.touch(mode=0o640, exist_ok=True)


def heartbeat_is_fresh(path: Path, *, max_age_seconds: int, now: float | None = None) -> bool:
    """Return whether a marker exists and has a plausible fresh mtime."""
    try:
        modified_at = path.stat().st_mtime
    except OSError:
        return False
    observed_at = time.time() if now is None else now
    age = observed_at - modified_at
    return -300 <= age <= max_age_seconds
