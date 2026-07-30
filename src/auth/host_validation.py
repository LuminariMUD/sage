"""Host-header validation settings for FastAPI apps."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable

_DEFAULT_ALLOWED_HOSTS = (
    "localhost",
    "127.0.0.1",
    "testserver",
    "api",
    "luminari-api",
)


def get_allowed_hosts(env_var: str = "ALLOWED_HOSTS") -> list[str]:
    """Load TrustedHostMiddleware hosts from JSON or comma-separated env."""
    raw = os.getenv(env_var, "")
    if not raw.strip():
        return list(_DEFAULT_ALLOWED_HOSTS)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = raw.split(",")

    if isinstance(parsed, str):
        parsed = parsed.split(",")

    if not isinstance(parsed, Iterable):
        return list(_DEFAULT_ALLOWED_HOSTS)

    hosts = [str(host).strip() for host in parsed if str(host).strip()]
    return hosts or list(_DEFAULT_ALLOWED_HOSTS)
