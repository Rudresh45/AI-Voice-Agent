"""Tests for knowledge domain endpoints and services."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Membership, Tenant, User


def test_knowledge_document_lifecycle(client: TestClient, db_session: Session):
    tenant = Tenant(name="Docs Corp", slug="docs-corp")
    user = User(external_id="idp|docs_user", email="docs@test.com")
    db_session.add_all([tenant, user])
    db_session.commit()

    membership = Membership(tenant_id=tenant.id, user_id=user.id, role="owner")
    db_session.add(membership)
    db_session.commit()

    headers = {"X-User-ID": str(user.id), "X-Tenant-ID": str(tenant.id)}

    # 1. Register document
    create_resp = client.post(
        "/api/v1/knowledge/",
        headers=headers,
        json={
            "title": "Onboarding Guide",
            "storage_key": "s3://bucket/docs/onboarding.pdf",
            "content_type": "application/pdf",
            "byte_size": 10240,
            "checksum_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        },
    )
    assert create_resp.status_code == 201
    doc_id = create_resp.json()["id"]

    # 2. Get document
    get_resp = client.get(f"/api/v1/knowledge/{doc_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Onboarding Guide"

    # 3. List documents
    list_resp = client.get("/api/v1/knowledge/", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["meta"]["total"] == 1

    # 4. Delete document
    del_resp = client.delete(f"/api/v1/knowledge/{doc_id}", headers=headers)
    assert del_resp.status_code == 204
