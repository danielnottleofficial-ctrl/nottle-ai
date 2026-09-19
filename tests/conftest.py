from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from nottle_ai.app import create_app
from nottle_ai.config import Settings


def make_settings(database_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "testing",
        "database_path": database_path,
        "app_secret": "test-secret-" * 6,
        "public_base_url": "https://nottle.example",
        "allowed_origins": ("https://localhost",),
        "allow_signups": True,
        "session_days": 30,
        "trial_days": 14,
        "openai_api_key": "test-openai-key",
        "openai_realtime_model": "gpt-realtime-2.1",
        "openai_voice": "marin",
        "openai_transcribe_model": "gpt-live-transcribe",
        "twilio_auth_token": "test-twilio-token",
        "verify_twilio_signature": False,
        "default_business_name": "DN Property Projects",
        "default_business_phone": "08 7666 3281",
        "default_business_area": "Perth, Western Australia",
        "support_email": "DNPropertyProjects@outlook.com",
        "admin_email": "",
        "admin_password": "",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_username": "",
        "smtp_password": "",
        "smtp_from": "",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path / "nottle-test.db")


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def register(
    client: TestClient,
    *,
    email: str = "alex@example.com",
    business_name: str = "Alex Electrical",
) -> dict:
    response = client.post(
        "/api/auth/register",
        json={
            "full_name": "Alex Morgan",
            "email": email,
            "password": "long-test-password",
            "business_name": business_name,
            "accept_terms": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
