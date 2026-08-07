"""Shared profile-aware client caches and one deterministic reset boundary."""

from __future__ import annotations

from typing import Any

text_provider_cache: dict[tuple[str, str], Any] = {}
embedder_cache: dict[tuple[str, str], Any] = {}


def reset_provider_caches() -> None:
    """Clear text and embedding clients without importing optional providers."""
    text_provider_cache.clear()
    embedder_cache.clear()
