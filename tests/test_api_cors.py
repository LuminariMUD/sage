"""Regression coverage for browser access to the authenticated chat API."""

from fastapi.testclient import TestClient

from src.api.main import app


def test_chat_stream_preflight_allows_ui_request_headers():
    """The static UI must be able to open its header-authenticated SSE stream."""
    client = TestClient(app)

    response = client.options(
        "/api/v1/chat/stream/test-stream",
        headers={
            "Origin": "http://127.0.0.1:8080",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-key,cache-control",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:8080"
    allowed_headers = response.headers["access-control-allow-headers"].lower()
    assert "x-api-key" in allowed_headers
    assert "cache-control" in allowed_headers
