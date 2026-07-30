"""
Authentication module for Luminari Sage API.

Provides multi-key authentication system following industry standards.
"""

from .api_key import KeyType, MultiKeyAuth
from .dependencies import RequireAPIKey, RequireMCPBackendKey, RequireMCPKey
from .exceptions import AuthenticationError, InvalidAPIKeyError, MissingAPIKeyError
from .middleware import AuthMiddleware

__all__ = [
    "AuthMiddleware",
    "AuthenticationError",
    "InvalidAPIKeyError",
    "KeyType",
    "MissingAPIKeyError",
    "MultiKeyAuth",
    "RequireAPIKey",
    "RequireMCPBackendKey",
    "RequireMCPKey",
]
