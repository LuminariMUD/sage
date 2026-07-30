"""
Multi-key authentication system for Luminari Sage services.

Following the wildeditor pattern for consistent authentication across services.
"""

import hashlib
import os
import secrets
from enum import Enum

from .exceptions import InvalidAPIKeyError, MissingAPIKeyError


class KeyType(Enum):
    """Available API key types for different Sage services."""

    BACKEND_API = "backend_api"
    MCP_OPERATIONS = "mcp_operations"
    MCP_BACKEND_ACCESS = "mcp_backend_access"


class MultiKeyAuth:
    """
    Multi-key authentication handler supporting three key types:
    - BACKEND_API: For direct backend API access (SAGE_API_KEY)
    - MCP_OPERATIONS: For MCP server operations (SAGE_MCP_KEY)
    - MCP_BACKEND_ACCESS: For MCP server to access backend (SAGE_MCP_BACKEND_KEY)
    """

    def __init__(self):
        """Initialize with environment variables."""
        self.keys: dict[KeyType, set[bytes]] = {
            KeyType.BACKEND_API: self._load_key("SAGE_API_KEY"),
            KeyType.MCP_OPERATIONS: self._load_key("SAGE_MCP_KEY"),
            KeyType.MCP_BACKEND_ACCESS: self._load_key("SAGE_MCP_BACKEND_KEY"),
        }

    @staticmethod
    def _fingerprint(api_key: str) -> bytes:
        """Return a fixed-size, non-reversible representation of an API key."""
        return hashlib.sha256(api_key.encode("utf-8")).digest()

    @classmethod
    def _load_key(cls, env_var: str) -> set[bytes]:
        """Load and fingerprint an API key, returning an empty set if unset."""
        key = os.getenv(env_var)
        return {cls._fingerprint(key)} if key else set()

    def is_valid_key(self, api_key: str, key_type: KeyType) -> bool:
        """Check if an API key is valid for the given key type."""
        if not api_key:
            return False
        candidate = self._fingerprint(api_key)
        return any(
            secrets.compare_digest(candidate, configured_key)
            for configured_key in self.keys.get(key_type, set())
        )

    def verify_key(self, api_key: str | None, key_type: KeyType) -> bool:
        """
        Verify an API key for the given key type.

        Args:
            api_key: The API key to verify
            key_type: The type of key expected

        Returns:
            True if valid

        Raises:
            MissingAPIKeyError: If no key provided
            InvalidAPIKeyError: If key is invalid
        """
        if not api_key:
            raise MissingAPIKeyError()

        if not self.is_valid_key(api_key, key_type):
            raise InvalidAPIKeyError(key_type.value)

        return True

    def add_key(self, api_key: str, key_type: KeyType) -> None:
        """Add a new API key for the given type."""
        if api_key:
            self.keys[key_type].add(self._fingerprint(api_key))

    def remove_key(self, api_key: str, key_type: KeyType) -> None:
        """Remove an API key for the given type."""
        self.keys[key_type].discard(self._fingerprint(api_key))

    def get_key_count(self, key_type: KeyType) -> int:
        """Get the number of valid keys for a given type."""
        return len(self.keys.get(key_type, set()))

    def has_valid_keys(self, key_type: KeyType) -> bool:
        """Check if there are any valid keys for the given type."""
        return self.get_key_count(key_type) > 0

    def is_auth_disabled(self) -> bool:
        """Check if authentication is disabled (for local development)."""
        return os.getenv("DISABLE_AUTH", "false").lower() == "true"
