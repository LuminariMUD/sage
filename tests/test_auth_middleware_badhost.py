from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth.middleware import AuthMiddleware


def test_auth_middleware_uses_scope_path_for_auth(monkeypatch):
    monkeypatch.delenv("DISABLE_AUTH", raising=False)
    monkeypatch.setenv("SAGE_API_KEY", "secret")

    app = FastAPI()
    app.add_middleware(
        AuthMiddleware,
        exclude_paths={"/docs"},
        backend_path_prefix="/api",
    )

    @app.get("/api/secret")
    def secret():
        return {"ok": True}

    client = TestClient(app)

    response = client.get(
        "/api/secret",
        headers={"Host": "testserver/docs?x="},
    )

    assert response.status_code == 401
    assert response.json()["type"] == "authentication_error"
