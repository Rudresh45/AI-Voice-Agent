"""Comprehensive security test suite for Phase 4: Identity, RBAC, and Multi-Tenant Security.

Tests include:
- Anonymous user rejection on protected endpoints.
- Session lifecycle, token hashing, revocation, and expiration.
- Brute-force rate limiting and safe credential error responses.
- Tenant isolation across agents, conversations, knowledge docs, and tools.
- UUID guessing prevention (no cross-tenant leakage).
- Read-only role write denial (HTTP 403).
- Security audit event generation.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.rate_limit import login_rate_limiter
from app.core.security import generate_session_token, hash_password, hash_session_token
from app.db.models import (
    Agent,
    AuditEvent,
    Conversation,
    KnowledgeDocument,
    Membership,
    MembershipRole,
    Tenant,
    ToolDefinition,
    User,
    UserSession,
)


def test_anonymous_user_rejected_on_protected_endpoints(client: TestClient):
    """Anonymous requests to protected resources must return 401 Unauthorized."""
    endpoints = [
        ("GET", "/api/v1/identity/me"),
        ("GET", "/api/v1/identity/sessions"),
        ("GET", "/api/v1/agents/"),
        ("POST", "/api/v1/agents/"),
        ("GET", "/api/v1/conversations/"),
        ("POST", "/api/v1/conversations/"),
        ("GET", "/api/v1/knowledge/"),
        ("POST", "/api/v1/knowledge/"),
        ("GET", "/api/v1/usage/"),
        ("GET", "/api/v1/audit/"),
    ]

    for method, path in endpoints:
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, json={})
        assert resp.status_code == 401, f"{method} {path} allowed anonymous access!"
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "UNAUTHORIZED"


def test_session_lifecycle_login_logout_and_revocation(client: TestClient, db_session: Session):
    """Verify session creation, authentication, logout revocation, and rejection of revoked tokens."""
    # Create user with hashed password
    user = User(
        external_id="idp|session_user",
        email="session_user@test.com",
        display_name="Session Tester",
        hashed_password=hash_password("SuperSecretPassword123!"),
    )
    db_session.add(user)
    db_session.commit()

    # 1. Login with credentials
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "session_user@test.com", "password": "SuperSecretPassword123!"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    token = login_data["session_token"]
    assert token.startswith("agyt_")

    headers = {"Authorization": f"Bearer {token}"}

    # 2. Access profile with active session
    profile_resp = client.get("/api/v1/identity/me", headers=headers)
    assert profile_resp.status_code == 200
    assert profile_resp.json()["user"]["email"] == "session_user@test.com"

    # 3. List active sessions
    sessions_resp = client.get("/api/v1/identity/sessions", headers=headers)
    assert sessions_resp.status_code == 200
    sessions = sessions_resp.json()
    assert len(sessions) >= 1
    assert sessions[0]["is_revoked"] is False

    # 4. Logout / Revoke session
    logout_resp = client.post("/api/v1/auth/logout", headers=headers)
    assert logout_resp.status_code == 200

    # 5. Subsequent request with revoked token MUST be rejected
    rejected_resp = client.get("/api/v1/identity/me", headers=headers)
    assert rejected_resp.status_code == 401
    assert rejected_resp.json()["error"]["code"] == "SESSION_REVOKED"


def test_expired_session_is_rejected(client: TestClient, db_session: Session):
    """Sessions with past expiration timestamps must be rejected immediately."""
    user = User(external_id="idp|expired_user", email="expired@test.com")
    db_session.add(user)
    db_session.commit()

    raw_token = generate_session_token()
    token_hash = hash_session_token(raw_token)
    expired_session = UserSession(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) - timedelta(hours=2),
    )
    db_session.add(expired_session)
    db_session.commit()

    headers = {"Authorization": f"Bearer {raw_token}"}
    resp = client.get("/api/v1/identity/me", headers=headers)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "SESSION_EXPIRED"


def test_login_rate_limiting_and_safe_errors(client: TestClient, db_session: Session):
    """Brute-force login attempts trigger rate limiting with constant-time generic error responses."""
    login_rate_limiter.reset()

    user = User(
        external_id="idp|target_user",
        email="target@test.com",
        hashed_password=hash_password("RealPassword123!"),
    )
    db_session.add(user)
    db_session.commit()

    # 5 consecutive bad password attempts
    for _ in range(5):
        resp = client.post(
            "/api/v1/auth/login",
            json={"email": "target@test.com", "password": "WrongPassword"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"]["message"] == "Invalid email or password."

    # 6th attempt must trigger 429 Too Many Requests
    rate_limited_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "target@test.com", "password": "WrongPassword"},
    )
    assert rate_limited_resp.status_code == 429
    assert rate_limited_resp.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    # Reset rate limiter
    login_rate_limiter.reset()

    # Querying non-existent user returns the EXACT same error message (no email enumeration)
    non_existent_resp = client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.com", "password": "AnyPassword"},
    )
    assert non_existent_resp.status_code == 401
    assert non_existent_resp.json()["error"]["message"] == "Invalid email or password."


def test_read_only_role_cannot_perform_writes(client: TestClient, db_session: Session):
    """Users with viewer/read_only roles can view resources but cannot mutate any data."""
    tenant = Tenant(name="Alpha Tenant", slug="alpha-tenant")
    user = User(external_id="idp|readonly_user", email="readonly@alpha.com")
    db_session.add_all([tenant, user])
    db_session.commit()

    # Assign READ_ONLY role
    membership = Membership(
        tenant_id=tenant.id,
        user_id=user.id,
        role=MembershipRole.READ_ONLY.value,
    )
    agent = Agent(
        tenant_id=tenant.id,
        name="Support Agent",
        instructions="Helpful support",
    )
    db_session.add_all([membership, agent])
    db_session.commit()

    headers = {"X-User-ID": str(user.id), "X-Tenant-ID": str(tenant.id)}

    # 1. READ is allowed
    get_resp = client.get("/api/v1/agents/", headers=headers)
    assert get_resp.status_code == 200
    assert len(get_resp.json()["data"]) == 1

    # 2. CREATE is blocked with 403 Forbidden
    create_agent_resp = client.post(
        "/api/v1/agents/",
        headers=headers,
        json={"name": "Hacked Agent", "instructions": "Malicious"},
    )
    assert create_agent_resp.status_code == 403
    assert create_agent_resp.json()["error"]["code"] == "PERMISSION_DENIED"

    # 3. UPDATE is blocked with 403 Forbidden
    patch_resp = client.patch(
        f"/api/v1/agents/{agent.id}",
        headers=headers,
        json={"name": "Altered Agent"},
    )
    assert patch_resp.status_code == 403
    assert patch_resp.json()["error"]["code"] == "PERMISSION_DENIED"

    # 4. DELETE is blocked with 403 Forbidden
    delete_resp = client.delete(f"/api/v1/agents/{agent.id}", headers=headers)
    assert delete_resp.status_code == 403
    assert delete_resp.json()["error"]["code"] == "PERMISSION_DENIED"

    # 5. Conversation creation blocked
    conv_resp = client.post(
        "/api/v1/conversations/",
        headers=headers,
        json={"agent_id": str(agent.id), "title": "Unauthorized Session"},
    )
    assert conv_resp.status_code == 403

    # 6. Knowledge document ingestion blocked
    doc_resp = client.post(
        "/api/v1/knowledge/",
        headers=headers,
        json={"title": "Unauthorized Doc", "content": "Text"},
    )
    assert doc_resp.status_code == 403


def test_cross_tenant_isolation_and_uuid_guessing(client: TestClient, db_session: Session):
    """Tenant B cannot read or modify Tenant A's agents, conversations, documents, or tools."""
    # Setup Tenant A
    tenant_a = Tenant(name="Tenant Alpha Corp", slug="tenant-alpha")
    user_a = User(external_id="idp|user_alpha", email="alpha@test.com")
    db_session.add_all([tenant_a, user_a])
    db_session.commit()
    m_a = Membership(tenant_id=tenant_a.id, user_id=user_a.id, role="owner")
    agent_a = Agent(tenant_id=tenant_a.id, name="Agent Alpha", instructions="Alpha prompt")
    conv_a = Conversation(tenant_id=tenant_a.id, user_id=user_a.id, agent_id=agent_a.id, title="Alpha Chat")
    doc_a = KnowledgeDocument(
        tenant_id=tenant_a.id,
        title="Alpha Secret Doc",
        storage_key="s3://alpha/docs/secret.txt",
        content_type="text/plain",
        byte_size=1024,
        checksum_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )
    tool_a = ToolDefinition(tenant_id=tenant_a.id, name="alpha_custom_tool", description="Alpha only", schema_json={})
    db_session.add_all([m_a, agent_a, conv_a, doc_a, tool_a])
    db_session.commit()

    # Setup Tenant B
    tenant_b = Tenant(name="Tenant Beta Corp", slug="tenant-beta")
    user_b = User(external_id="idp|user_beta", email="beta@test.com")
    db_session.add_all([tenant_b, user_b])
    db_session.commit()
    m_b = Membership(tenant_id=tenant_b.id, user_id=user_b.id, role="owner")
    db_session.add(m_b)
    db_session.commit()

    headers_b = {"X-User-ID": str(user_b.id), "X-Tenant-ID": str(tenant_b.id)}

    # Attempting to read or mutate Tenant A's objects using exact guessed UUIDs
    # Agent lookup -> 404 (does NOT reveal existence)
    resp = client.get(f"/api/v1/agents/{agent_a.id}", headers=headers_b)
    assert resp.status_code == 404

    # Agent update -> 403 or 404 (cross-tenant access denied)
    resp = client.patch(f"/api/v1/agents/{agent_a.id}", headers=headers_b, json={"name": "Hijacked"})
    assert resp.status_code in (403, 404)

    # Agent delete -> 403 or 404
    resp = client.delete(f"/api/v1/agents/{agent_a.id}", headers=headers_b)
    assert resp.status_code in (403, 404)

    # Conversation lookup -> 403 or 404
    resp = client.get(f"/api/v1/conversations/{conv_a.id}", headers=headers_b)
    assert resp.status_code in (403, 404)

    # Document lookup -> 403 or 404
    resp = client.get(f"/api/v1/knowledge/{doc_a.id}", headers=headers_b)
    assert resp.status_code in (403, 404)

    # Document delete -> 403 or 404
    resp = client.delete(f"/api/v1/knowledge/{doc_a.id}", headers=headers_b)
    assert resp.status_code in (403, 404)

    # Tool definition lookup -> 403 or 404
    resp = client.get(f"/api/v1/integrations/tools/{tool_a.id}", headers=headers_b)
    assert resp.status_code in (403, 404)


def test_client_supplied_tenant_id_never_proof_of_access(client: TestClient, db_session: Session):
    """Supplying another tenant's ID in header must be rejected with 403 Forbidden."""
    tenant_target = Tenant(name="Target Tenant", slug="target-tenant")
    user_stranger = User(external_id="idp|stranger", email="stranger@test.com")
    db_session.add_all([tenant_target, user_stranger])
    db_session.commit()

    # Stranger tries to pass Target Tenant's ID
    headers = {"X-User-ID": str(user_stranger.id), "X-Tenant-ID": str(tenant_target.id)}
    resp = client.get("/api/v1/agents/", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


def test_server_side_tenant_resolution_without_header(client: TestClient, db_session: Session):
    """When X-Tenant-ID is omitted, system resolves the user's active tenant automatically."""
    tenant = Tenant(name="Auto Resolve Tenant", slug="auto-resolve")
    user = User(external_id="idp|auto_user", email="auto@test.com")
    db_session.add_all([tenant, user])
    db_session.commit()

    membership = Membership(tenant_id=tenant.id, user_id=user.id, role="member")
    agent = Agent(tenant_id=tenant.id, name="Auto Agent", instructions="Auto prompt")
    db_session.add_all([membership, agent])
    db_session.commit()

    # Omit X-Tenant-ID completely
    headers = {"X-User-ID": str(user.id)}
    resp = client.get("/api/v1/agents/", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()["data"]) == 1
    assert resp.json()["data"][0]["name"] == "Auto Agent"


def test_audit_event_generation_on_sensitive_actions(client: TestClient, db_session: Session):
    """Verify that tenant creation and member invitations record audit events."""
    user = User(external_id="idp|auditor", email="auditor@test.com")
    db_session.add(user)
    db_session.commit()

    headers = {"X-User-ID": str(user.id)}

    # 1. Create Tenant -> records audit event
    create_tenant_resp = client.post(
        "/api/v1/tenants/",
        headers=headers,
        json={"name": "Audited Organization", "slug": "audited-org"},
    )
    assert create_tenant_resp.status_code == 201
    tenant_id = create_tenant_resp.json()["id"]

    # 2. Invite Member -> records audit event
    headers["X-Tenant-ID"] = tenant_id
    invite_resp = client.post(
        f"/api/v1/tenants/{tenant_id}/members",
        headers=headers,
        json={"email": "newmember@audited.com", "role": "member"},
    )
    assert invite_resp.status_code == 201

    # Verify audit records in DB
    events = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.tenant_id == uuid.UUID(tenant_id))
        .all()
    )
    action_types = [e.action for e in events]
    assert "tenant.create" in action_types
    assert "tenant.member_invited" in action_types
