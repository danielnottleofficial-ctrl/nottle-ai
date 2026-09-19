from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import auth, register


def test_public_shell_and_health(client: TestClient) -> None:
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True
    assert health.json()["service"] == "NOTTLE AI"

    assert "Every call answered" in client.get("/").text
    assert "Privacy Policy" in client.get("/privacy").text
    assert client.get("/manifest.json").json()["short_name"] == "NOTTLE AI"


def test_customer_lifecycle(client: TestClient) -> None:
    created = register(client)
    headers = auth(created["token"])

    me = client.get("/api/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["business"]["name"] == "Alex Electrical"

    updated = client.patch(
        "/api/business",
        headers=headers,
        json={
            "industry": "Electrical",
            "services": "Fault finding, switchboards",
            "conversation_pace": "patient",
            "onboarding_completed": True,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["business"]["onboarding_completed"] is True

    dashboard = client.get("/api/dashboard", headers=headers).json()
    assert dashboard["stats"] == {
        "calls": 0,
        "leads": 0,
        "bookings": 0,
        "seconds": 0,
    }
    assert dashboard["trial_expired"] is False

    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/me", headers=headers).status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"email": "ALEX@example.com", "password": "long-test-password"},
    )
    assert login.status_code == 200


def test_registration_validation_and_duplicate(client: TestClient) -> None:
    weak = client.post(
        "/api/auth/register",
        json={
            "full_name": "Alex Morgan",
            "email": "not-an-email",
            "password": "short",
            "business_name": "Alex Electrical",
            "accept_terms": False,
        },
    )
    assert weak.status_code == 422

    register(client)
    duplicate = client.post(
        "/api/auth/register",
        json={
            "full_name": "Another Alex",
            "email": "alex@example.com",
            "password": "another-long-password",
            "business_name": "Another Business",
            "accept_terms": True,
        },
    )
    assert duplicate.status_code == 409


def test_tenant_call_isolation_and_deletion(client: TestClient, app) -> None:
    first = register(client, email="first@example.com", business_name="First Co")
    second = register(client, email="second@example.com", business_name="Second Co")
    db = app.state.database
    first_business = db.business_for_user(first["user"]["id"])
    second_business = db.business_for_user(second["user"]["id"])

    first_call = db.create_call(
        business_id=first_business["id"],
        stream_sid="MS1",
        call_sid="CA1",
        caller="+61400000001",
        called_number="+61800000001",
    )
    db.finish_call(
        first_call,
        status="completed",
        transcript="Caller: I need a quote",
        summary="Booking or quote request",
        booking_requested=True,
        duration_seconds=42,
    )
    second_call = db.create_call(
        business_id=second_business["id"],
        stream_sid="MS2",
        call_sid="CA2",
        caller="+61400000002",
        called_number="+61800000002",
    )

    first_headers = auth(first["token"])
    calls = client.get("/api/calls", headers=first_headers).json()["calls"]
    assert [row["id"] for row in calls] == [first_call]
    assert client.get(f"/api/calls/{second_call}", headers=first_headers).status_code == 404
    assert client.delete(f"/api/calls/{first_call}", headers=first_headers).status_code == 204
    assert client.get("/api/calls", headers=first_headers).json()["calls"] == []


def test_export_and_account_deletion(client: TestClient) -> None:
    created = register(client)
    headers = auth(created["token"])
    export = client.get("/api/account/export", headers=headers)
    assert export.status_code == 200
    assert export.json()["user"]["email"] == "alex@example.com"

    refused = client.request(
        "DELETE",
        "/api/account",
        headers=headers,
        json={"password": "long-test-password", "confirmation": "no"},
    )
    assert refused.status_code == 400
    deleted = client.request(
        "DELETE",
        "/api/account",
        headers=headers,
        json={"password": "long-test-password", "confirmation": "DELETE"},
    )
    assert deleted.status_code == 204
    assert client.get("/api/me", headers=headers).status_code == 401


def test_voice_routes_only_known_active_number(client: TestClient) -> None:
    accepted = client.post(
        "/voice",
        data={
            "To": "+61876663281",
            "From": "+61400000000",
            "CallSid": "CA123",
        },
    )
    assert accepted.status_code == 200
    assert "<Connect><Stream" in accepted.text
    assert "wss://nottle.example/media-stream" in accepted.text
    assert "AI assistant" not in accepted.text

    unknown = client.post(
        "/voice",
        data={"To": "+61811111111", "From": "+61400000000"},
    )
    assert unknown.status_code == 200
    assert "<Reject/>" in unknown.text
