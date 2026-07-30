"""
FastAPI dependency functions for authentication in Luminari Sage API.
"""

from fastapi import Depends, Header, HTTPException

from .api_key import KeyType, MultiKeyAuth
from .exceptions import AuthenticationError

# Global auth instance
auth_instance = MultiKeyAuth()


async def verify_api_key(x_api_key: str | None = Header(None)) -> bool:
    """Verify backend API key (SAGE_API_KEY)."""
    if auth_instance.is_auth_disabled():
        return True

    try:
        return auth_instance.verify_key(x_api_key, KeyType.BACKEND_API)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "message": e.detail,
                "type": "authentication_error",
                "required_header": "X-API-Key",
                "key_type": "backend_api",
            },
        )


async def verify_mcp_key(x_api_key: str | None = Header(None)) -> bool:
    """Verify MCP operations key (SAGE_MCP_KEY)."""
    if auth_instance.is_auth_disabled():
        return True

    try:
        return auth_instance.verify_key(x_api_key, KeyType.MCP_OPERATIONS)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "message": e.detail,
                "type": "authentication_error",
                "required_header": "X-API-Key",
                "key_type": "mcp_operations",
            },
        )


async def verify_mcp_backend_key(x_api_key: str | None = Header(None)) -> bool:
    """Verify MCP backend access key (SAGE_MCP_BACKEND_KEY)."""
    if auth_instance.is_auth_disabled():
        return True

    try:
        return auth_instance.verify_key(x_api_key, KeyType.MCP_BACKEND_ACCESS)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "message": e.detail,
                "type": "authentication_error",
                "required_header": "X-API-Key",
                "key_type": "mcp_backend_access",
            },
        )


def get_auth_dependency(key_type: KeyType):
    """
    Factory function to create auth dependencies for specific key types.

    Args:
        key_type: The type of key to verify

    Returns:
        FastAPI dependency function
    """

    async def verify_key_dependency(x_api_key: str | None = Header(None)) -> bool:
        if auth_instance.is_auth_disabled():
            return True

        try:
            return auth_instance.verify_key(x_api_key, key_type)
        except AuthenticationError as e:
            raise HTTPException(
                status_code=e.status_code,
                detail={
                    "message": e.detail,
                    "type": "authentication_error",
                    "required_header": "X-API-Key",
                    "key_type": key_type.value,
                },
            )

    return verify_key_dependency


# Convenience dependencies for common use cases
RequireAPIKey = Depends(verify_api_key)
RequireMCPKey = Depends(verify_mcp_key)
RequireMCPBackendKey = Depends(verify_mcp_backend_key)
