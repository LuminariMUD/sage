"""Regression tests for fail-closed path authentication.

Paths outside the /api and /mcp prefixes used to bypass authentication
entirely, which left the /debug/* auth-introspection endpoints publicly
readable. Unknown paths must now require the backend API key.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth.middleware import AuthMiddleware


def _build_client(monkeypatch):
    monkeypatch.delenv("DISABLE_AUTH", raising=False)
    monkeypatch.setenv("SAGE_API_KEY", "secret")

    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/debug/auth-env")
    def debug_auth_env():
        return {"DISABLE_AUTH": "NOT SET"}

    return TestClient(app)


def test_debug_path_requires_api_key(monkeypatch):
    client = _build_client(monkeypatch)

    response = client.get("/debug/auth-env")

    assert response.status_code == 401
    assert response.json()["type"] == "authentication_error"


def test_debug_path_allows_valid_api_key(monkeypatch):
    client = _build_client(monkeypatch)

    response = client.get("/debug/auth-env", headers={"X-API-Key": "secret"})

    assert response.status_code == 200


def test_excluded_paths_remain_public(monkeypatch):
    client = _build_client(monkeypatch)

    assert client.get("/ping").status_code in (200, 404)
    assert client.get("/ping").status_code != 401


def test_health_prefix_does_not_create_an_auth_bypass(monkeypatch):
    client = _build_client(monkeypatch)

    response = client.get("/api/v1/health/private")

    assert response.status_code == 401
    assert response.json()["type"] == "authentication_error"
