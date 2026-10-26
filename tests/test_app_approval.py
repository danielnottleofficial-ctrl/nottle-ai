from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from nottle_ai.app import create_app
from nottle_ai.bookings import Bookings
from nottle_ai.push import Push
from nottle_ai.security import token_hash
from tests.test_bookings import setup, drain


def app_service(fixture):
    settings, db, _, code, sent, events, business, call_id = fixture
    service = Bookings(db, replace(settings, app_approval_enabled=True))
    service.calendar = lambda *args: events.append(code) or 'event1'
    service.sms = lambda *args: pytest.fail('App workflow must never send Twilio SMS')
    return service, db, code, events, business


def test_confirmation_only_and_idempotence(setup, monkeypatch):
    service, db, code, events, business = app_service(setup)
    monkeypatch.setattr(Push, 'send', lambda *args: None)
    drain(service)
    assert events == []
    assert service.app_decide(business['id'], code, 'confirm') == 'approved'
    assert service.app_decide(business['id'], code, 'confirm') == 'approved'
    drain(service)
    assert events == [code]
    assert service.app_decide(business['id'], code, 'decline') == 'confirmed'
    with db.connect() as conn:
        assert not conn.execute("SELECT 1 FROM booking_jobs WHERE kind='customer'").fetchone()


def test_decline_does_not_create_event_or_send_sms(setup):
    service, _, code, events, business = app_service(setup)
    assert service.app_decide(business['id'], code, 'decline') == 'declined'
    drain(service)
    assert not events


def test_wrong_business_and_missing_calendar_leave_pending(setup):
    service, db, code, _, business = app_service(setup)
    with pytest.raises(LookupError):
        service.app_decide(business['id']+99, code, 'confirm')
    service.settings = replace(service.settings, google_refresh_token='')
    with pytest.raises(ValueError, match='not connected'):
        service.app_decide(business['id'], code, 'confirm')
    with db.connect() as conn:
        assert conn.execute('SELECT status FROM booking_requests WHERE id=?',(code,)).fetchone()[0] == 'pending'


def test_push_registration_session_logout_and_cross_tenant_api(setup):
    settings, db, _, code, _, _, business, call_id = setup
    app = create_app(replace(settings, app_approval_enabled=True))
    user, other_business = db.create_user_and_business(email='other@example.com',password_hash='unused',full_name='Other owner',business_name='Other business')
    token = 'a-test-session-token'
    db.create_session(token,user['id'],'test')
    client = TestClient(app)
    headers = {'Authorization': 'Bearer '+token}
    assert client.post('/api/push/register',json={'token':'x'*50}).status_code == 401
    assert client.post('/api/push/register',json={'token':'x'*50},headers=headers).status_code == 200
    assert client.get(f'/api/calls/{call_id}/booking',headers=headers).json()['booking'] is None
    assert client.post(f'/api/bookings/{code}/decision',json={'action':'confirm'},headers=headers).status_code == 404
    with db.connect() as conn:
        assert conn.execute('SELECT session_hash FROM push_devices').fetchone()[0] == token_hash(token)
    client.post('/api/auth/logout',headers=headers)
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM push_devices').fetchone()[0] == 0
