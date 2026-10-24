"""Integration tests for core API behavior, error envelopes, and middleware."""

import uuid
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import Agent, Membership, Tenant, User
from app.main import app


def test_request_id_middleware_propagation(client: TestClient):
    custom_req_id = "custom-test-req-12345"
    resp = client.get("/health/live", headers={"X-Request-ID": custom_req_id})
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-ID") == custom_req_id

    # If no header provided, middleware should generate a UUID
    resp_no_header = client.get("/health/live")
    assert resp_no_header.status_code == 200
    auto_id = resp_no_header.headers.get("X-Request-ID")
    assert auto_id is not None
    assert len(auto_id) > 10


def test_standardized_validation_error_envelope(client: TestClient, db_session: Session):
    # Missing required fields or invalid format
    tenant = Tenant(name="Envelope Corp", slug="envelope-corp")
    user = User(external_id="idp|envelope_u", email="envelope@test.com")
    db_session.add_all([tenant, user])
    db_session.commit()
    membership = Membership(tenant_id=tenant.id, user_id=user.id, role="owner")
    db_session.add(membership)
    db_session.commit()

    headers = {
        "X-User-ID": str(user.id),
        "X-Tenant-ID": str(tenant.id),
        "X-Request-ID": "validation-err-req",
    }
    # Send empty body where agent create expects name and instructions
    resp = client.post("/api/v1/agents/", headers=headers, json={})
    assert resp.status_code == 422
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["request_id"] == "validation-err-req"
    assert isinstance(data["error"]["details"], list)


def test_standardized_entity_not_found_error_envelope(client: TestClient, db_session: Session):
    tenant = Tenant(name="Lookup Corp", slug="lookup-corp")
    user = User(external_id="idp|lookup_u", email="lookup@test.com")
    db_session.add_all([tenant, user])
    db_session.commit()
    membership = Membership(tenant_id=tenant.id, user_id=user.id, role="owner")
    db_session.add(membership)
    db_session.commit()

    headers = {
        "X-User-ID": str(user.id),
        "X-Tenant-ID": str(tenant.id),
        "X-Request-ID": "not-found-req",
    }
    random_uuid = uuid.uuid4()
    resp = client.get(f"/api/v1/agents/{random_uuid}", headers=headers)
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "ENTITY_NOT_FOUND"
    assert data["error"]["request_id"] == "not-found-req"
    assert data["error"]["details"]["id"] == str(random_uuid)


def test_cross_tenant_access_denied_envelope(client: TestClient, db_session: Session):
    # Tenant 1 has agent
    t1 = Tenant(name="Tenant A", slug="tenant-a")
    u1 = User(external_id="idp|user_a", email="usera@test.com")
    db_session.add_all([t1, u1])
    db_session.commit()
    m1 = Membership(tenant_id=t1.id, user_id=u1.id, role="owner")
    db_session.add(m1)
    agent = Agent(
        tenant_id=t1.id,
        name="Secret Agent",
        instructions="Classified agent instructions",
    )
    db_session.add(agent)
    db_session.commit()

    # Tenant 2 user tries to access Tenant 1's agent
    t2 = Tenant(name="Tenant B", slug="tenant-b")
    u2 = User(external_id="idp|user_b", email="userb@test.com")
    db_session.add_all([t2, u2])
    db_session.commit()
    m2 = Membership(tenant_id=t2.id, user_id=u2.id, role="owner")
    db_session.add(m2)
    db_session.commit()

    headers_b = {
        "X-User-ID": str(u2.id),
        "X-Tenant-ID": str(t2.id),
        "X-Request-ID": "cross-tenant-req",
    }
    # Cross-tenant ID lookup should securely return 404 Entity Not Found (preventing enumeration)
    resp = client.get(f"/api/v1/agents/{agent.id}", headers=headers_b)
    assert resp.status_code == 404
    data = resp.json()
    assert "error" in data
    assert data["error"]["code"] == "ENTITY_NOT_FOUND"
    assert data["error"]["request_id"] == "cross-tenant-req"


def test_safe_database_failure_envelope(client: TestClient, db_session: Session):
    # When a database query fails with a SQLAlchemyError, raw SQL must never leak
    user = User(external_id="idp|db_err_user", email="dberr@test.com")
    db_session.add(user)
    db_session.commit()

    def failing_db():
        mock = MagicMock(spec=Session)
        mock.get.side_effect = SQLAlchemyError(
            "FATAL: connection terminated unexpectedly SELECT * FROM secrets"
        )
        mock.scalar.side_effect = SQLAlchemyError(
            "FATAL: connection terminated unexpectedly SELECT * FROM secrets"
        )
        mock.execute.side_effect = SQLAlchemyError(
            "FATAL: connection terminated unexpectedly SELECT * FROM secrets"
        )
        yield mock

    app.dependency_overrides[get_db] = failing_db
    try:
        resp = client.get(
            "/api/v1/identity/me",
            headers={"X-User-ID": str(user.id), "X-Request-ID": "sql-err-req"},
        )
        assert resp.status_code == 500
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "DATABASE_ERROR"
        assert "secrets" not in str(data)  # SQL details not leaked to user
    finally:
        app.dependency_overrides.clear()


def test_openapi_documentation_accessible(client: TestClient):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "AI Voice Platform"
    assert "/api/v1/identity/me" in schema["paths"]
    assert "/api/v1/tenants/" in schema["paths"]
    assert "/api/v1/agents/" in schema["paths"]
    assert "/api/v1/conversations/" in schema["paths"]
    assert "/api/v1/knowledge/" in schema["paths"]
    assert "/api/v1/integrations/tools" in schema["paths"]
    assert "/api/v1/usage/" in schema["paths"]
    assert "/api/v1/audit/" in schema["paths"]
    assert "/api/v1/platform-ops/health" in schema["paths"]
