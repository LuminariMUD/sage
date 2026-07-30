"""
Authentication exceptions for Luminari Sage API.
"""


class AuthenticationError(Exception):
    """Base authentication error."""

    def __init__(self, message: str, status_code: int = 401):
        self.message = message
        self.status_code = status_code
        self.detail = message
        super().__init__(self.message)


class MissingAPIKeyError(AuthenticationError):
    """Raised when no API key is provided."""

    def __init__(self):
        super().__init__(
            "API key required. Include 'X-API-Key' header with your request.", status_code=401
        )


class InvalidAPIKeyError(AuthenticationError):
    """Raised when an invalid API key is provided."""

    def __init__(self, key_type: str | None = None):
        message = "Invalid API key"
        if key_type:
            message += f" for {key_type}"
        message += ". Check your 'X-API-Key' header value."

        super().__init__(message, status_code=401)
