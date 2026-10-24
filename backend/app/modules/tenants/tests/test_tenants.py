"""Tests for tenants domain endpoints and services."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import User


def test_create_tenant_and_assign_owner(client: TestClient, db_session: Session):
    user = User(external_id="idp|owner_test", email="owner@test.com")
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/v1/tenants/",
        headers={"X-User-ID": str(user.id)},
        json={"name": "New Venture", "slug": "new-venture"},
    )
    assert response.status_code == 201
    tenant_data = response.json()
    assert tenant_data["name"] == "New Venture"
    assert tenant_data["slug"] == "new-venture"

    # List members
    members_resp = client.get(
        f"/api/v1/tenants/{tenant_data['id']}/members",
        headers={"X-User-ID": str(user.id)},
    )
    assert members_resp.status_code == 200
    members = members_resp.json()
    assert len(members) == 1
    assert members[0]["role"] == "owner"


def test_tenant_access_denied_for_non_member(client: TestClient, db_session: Session):
    owner = User(external_id="idp|owner1", email="owner1@test.com")
    intruder = User(external_id="idp|intruder", email="intruder@test.com")
    db_session.add_all([owner, intruder])
    db_session.commit()

    # Create tenant as owner
    create_resp = client.post(
        "/api/v1/tenants/",
        headers={"X-User-ID": str(owner.id)},
        json={"name": "Private Org", "slug": "private-org"},
    )
    tenant_id = create_resp.json()["id"]

    # Intruder attempts access
    resp = client.get(
        f"/api/v1/tenants/{tenant_id}",
        headers={"X-User-ID": str(intruder.id)},
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"
