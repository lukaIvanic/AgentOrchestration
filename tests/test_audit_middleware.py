from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from src.api.middleware import (
    AuditMiddleware,
    AuthMiddleware,
    get_current_audit_actor,
)
from src.api.server import create_app


def _protected_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/v2/protected")
    async def protected(request: Request):
        return {
            "audit_actor": request.state.audit_actor,
            "context_actor": get_current_audit_actor(),
        }

    @app.get("/api/v2/fail")
    async def fail(request: Request):
        assert request.state.audit_actor == get_current_audit_actor()
        raise RuntimeError("boom")

    @app.get("/api/v2/auth/token")
    async def token():
        return {"status": "public"}

    app.add_middleware(AuditMiddleware)
    app.add_middleware(AuthMiddleware)
    return app


def test_audit_actor_is_attached_after_auth_succeeds():
    client = TestClient(_protected_app())

    response = client.get(
        "/api/v2/protected",
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["audit_actor"].startswith("bearer:")
    assert payload["audit_actor"] == payload["context_actor"]
    assert payload["audit_actor"] != "secret-token"
    assert response.headers["X-Audit-Status"] == "accepted"
    assert response.headers["X-Audit-Actor"] == payload["audit_actor"]
    assert "secret-token" not in response.headers["X-Audit-Actor"]
    assert get_current_audit_actor() is None


def test_missing_auth_fails_before_audit_state_reaches_handler():
    client = TestClient(_protected_app())

    response = client.get("/api/v2/protected")

    assert response.status_code == 401
    assert response.headers["X-Audit-Status"] == "rejected"
    assert "X-Audit-Actor" not in response.headers
    assert get_current_audit_actor() is None


def test_blank_bearer_token_is_rejected_before_audit_state():
    client = TestClient(_protected_app())

    response = client.get(
        "/api/v2/protected",
        headers={"Authorization": "Bearer   "},
    )

    assert response.status_code == 401
    assert response.headers["X-Audit-Status"] == "rejected"
    assert "X-Audit-Actor" not in response.headers
    assert get_current_audit_actor() is None


def test_public_token_route_does_not_attach_audit_actor():
    client = TestClient(_protected_app())

    response = client.get("/api/v2/auth/token")

    assert response.status_code == 200
    assert "X-Audit-Status" not in response.headers
    assert get_current_audit_actor() is None


def test_audit_context_is_cleared_when_handler_raises():
    client = TestClient(_protected_app(), raise_server_exceptions=False)

    response = client.get(
        "/api/v2/fail",
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 500
    assert get_current_audit_actor() is None


def test_create_app_orders_auth_before_audit_for_protected_routes():
    client = TestClient(create_app())

    unauthenticated = client.get("/api/v2/agents")
    authenticated = client.get(
        "/api/v2/agents",
        headers={"Authorization": "Bearer secret-token"},
    )

    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["X-Audit-Status"] == "rejected"
    assert "X-Audit-Actor" not in unauthenticated.headers
    assert authenticated.status_code == 200
    assert authenticated.headers["X-Audit-Status"] == "accepted"
    assert authenticated.headers["X-Audit-Actor"].startswith("bearer:")
    assert get_current_audit_actor() is None


def test_rejected_and_accepted_audit_logs_are_sanitized(caplog):
    client = TestClient(_protected_app())

    with caplog.at_level("INFO", logger="src.api.middleware"):
        rejected = client.get(
            "/api/v2/protected",
            headers={"Authorization": "Bearer   "},
        )
        accepted = client.get(
            "/api/v2/protected",
            headers={"Authorization": "Bearer secret-token"},
        )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert "blank_bearer" in caplog.text
    assert "audit accepted protected request for bearer:" in caplog.text
    assert "secret-token" not in caplog.text
