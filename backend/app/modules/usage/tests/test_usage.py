"""Tests for usage domain endpoints and services."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Membership, Tenant, User


def test_record_and_aggregate_usage(client: TestClient, db_session: Session):
    tenant = Tenant(name="Usage Corp", slug="usage-corp")
    user = User(external_id="idp|usage_user", email="usage@test.com")
    db_session.add_all([tenant, user])
    db_session.commit()

    membership = Membership(tenant_id=tenant.id, user_id=user.id, role="member")
    db_session.add(membership)
    db_session.commit()

    headers = {"X-User-ID": str(user.id), "X-Tenant-ID": str(tenant.id)}

    # Record 2 usage events
    client.post(
        "/api/v1/usage/",
        headers=headers,
        json={"event_type": "gemini_tokens", "quantity": 100, "unit": "tokens"},
    )
    client.post(
        "/api/v1/usage/",
        headers=headers,
        json={"event_type": "gemini_tokens", "quantity": 150, "unit": "tokens"},
    )
    client.post(
        "/api/v1/usage/",
        headers=headers,
        json={"event_type": "whisper_seconds", "quantity": 30, "unit": "seconds"},
    )

    # Get aggregated summary
    summary_resp = client.get("/api/v1/usage/", headers=headers)
    assert summary_resp.status_code == 200
    summary = summary_resp.json()["summary"]
    token_item = next(item for item in summary if item["event_type"] == "gemini_tokens")
    assert token_item["total_quantity"] == 250
    audio_item = next(item for item in summary if item["event_type"] == "whisper_seconds")
    assert audio_item["total_quantity"] == 30
