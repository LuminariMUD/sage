"""
FastAPI middleware for automatic authentication in Luminari Sage API.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .api_key import KeyType, MultiKeyAuth
from .exceptions import AuthenticationError


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware to automatically authenticate requests based on path.

    Routes authentication based on path prefixes:
    - /api/* requires BACKEND_API key
    - /mcp/* requires MCP_OPERATIONS key
    - Excluded paths bypass authentication
    """

    def __init__(
        self,
        app,
        exclude_paths: set[str] | None = None,
        mcp_path_prefix: str = "/mcp",
        backend_path_prefix: str = "/api",
    ):
        """
        Initialize auth middleware.

        Args:
            app: FastAPI application
            exclude_paths: Paths to exclude from authentication
            mcp_path_prefix: Path prefix for MCP endpoints
            backend_path_prefix: Path prefix for backend endpoints
        """
        super().__init__(app)
        self.auth = MultiKeyAuth()
        self.exclude_paths = exclude_paths or {
            "/health",
            "/api/v1/health",
            "/ping",
            "/docs",
            "/redoc",
            "/openapi.json",
            "/favicon.ico",
        }
        # Add exact root path separately to avoid startswith issues
        self.exclude_root = True
        self.mcp_path_prefix = mcp_path_prefix
        self.backend_path_prefix = backend_path_prefix

    async def dispatch(self, request: Request, call_next):
        """Process request through authentication."""
        path = str(request.scope.get("path", ""))

        # Skip authentication for OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip authentication if disabled (for local development)
        if self.auth.is_auth_disabled():
            return await call_next(request)

        # Skip authentication for excluded paths
        if self._should_exclude_path(path):
            return await call_next(request)

        # Get API key from header
        api_key = request.headers.get("X-API-Key")

        # Determine required key type based on path
        key_type = self._determine_key_type(path)

        if key_type is None:
            # Path doesn't require authentication
            return await call_next(request)

        # Verify authentication
        try:
            self.auth.verify_key(api_key, key_type)
        except AuthenticationError as e:
            # For /api/* endpoints, also try MCP_BACKEND_ACCESS key for internal service calls
            if key_type == KeyType.BACKEND_API:
                try:
                    self.auth.verify_key(api_key, KeyType.MCP_BACKEND_ACCESS)
                    # If MCP_BACKEND_ACCESS key works, continue
                except AuthenticationError:
                    # Both keys failed, return original error
                    return JSONResponse(
                        status_code=e.status_code,
                        content={
                            "detail": e.detail,
                            "type": "authentication_error",
                            "required_header": "X-API-Key",
                        },
                    )
            else:
                return JSONResponse(
                    status_code=e.status_code,
                    content={
                        "detail": e.detail,
                        "type": "authentication_error",
                        "required_header": "X-API-Key",
                    },
                )

        # Continue with authenticated request
        response = await call_next(request)
        return response

    def _should_exclude_path(self, path: str) -> bool:
        """Check if path should be excluded from authentication."""
        # Handle exact root path
        if self.exclude_root and path == "/":
            return True

        if path in self.exclude_paths:
            return True

        # Interactive documentation has a nested OAuth redirect route. Health
        # and ping exclusions remain exact so a similarly prefixed future route
        # cannot accidentally become public.
        return any(
            path.startswith(f"{prefix}/")
            for prefix in ("/docs", "/redoc")
            if prefix in self.exclude_paths
        )

    def _determine_key_type(self, path: str) -> KeyType | None:
        """
        Determine required key type based on request path.

        Args:
            path: Request path

        Returns:
            Required KeyType (never None - unknown paths fail closed)
        """
        if path.startswith(self.mcp_path_prefix):
            return KeyType.MCP_OPERATIONS
        elif path.startswith(self.backend_path_prefix):
            return KeyType.BACKEND_API

        # Fail closed: any path not explicitly excluded requires the backend key.
        # Without this, a new route outside /api and /mcp would be served
        # anonymously (e.g. the /debug/* auth-introspection endpoints).
        return KeyType.BACKEND_API
