"""Tests for identity domain endpoints and services."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Membership, Tenant, User


def test_get_current_user_profile(client: TestClient, db_session: Session):
    tenant = Tenant(name="Identity Org", slug="identity-org")
    user = User(external_id="idp|alice_id", email="alice@identity.test", display_name="Alice")
    db_session.add_all([tenant, user])
    db_session.commit()

    membership = Membership(tenant_id=tenant.id, user_id=user.id, role="owner")
    db_session.add(membership)
    db_session.commit()

    response = client.get("/api/v1/identity/me", headers={"X-User-ID": str(user.id)})
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == "alice@identity.test"
    assert data["user"]["display_name"] == "Alice"
    assert len(data["memberships"]) == 1


def test_update_current_user_profile(client: TestClient, db_session: Session):
    user = User(external_id="idp|bob_id", email="bob@identity.test", display_name="Bob Original")
    db_session.add(user)
    db_session.commit()

    response = client.patch(
        "/api/v1/identity/me",
        headers={"X-User-ID": str(user.id)},
        json={"display_name": "Bob Updated"},
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Bob Updated"
