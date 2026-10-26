import base64
import hashlib
import hmac
import json
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from nottle_ai.app import create_app
from nottle_ai.bookings import Bookings
from nottle_ai.database import Database
from tests.conftest import make_settings


@pytest.fixture
def setup(tmp_path, monkeypatch):
    settings = make_settings(tmp_path / 'bookings.db', booking_approval_enabled=True,
        twilio_account_sid='ACtest', twilio_messaging_from='+61400000001',
        sms_summary_recipient='+61400000002', google_client_id='client',
        google_client_secret='secret', google_refresh_token='refresh')
    db = Database(settings.database_path, settings)
    db.init()
    service = Bookings(db, settings)
    business = db.business_by_phone(settings.default_business_phone)
    call_id = db.create_call(business_id=business['id'], stream_sid='MZtest',
                            call_sid='CAtest', caller='+61400000003', called_number=settings.default_business_phone)
    db.finish_call(call_id, status='completed', transcript='Caller: A booking please', summary='Booking',
                   booking_requested=True, duration_seconds=60, error_message='')
    start = (datetime.now(ZoneInfo('Australia/Perth')) + timedelta(days=2)).replace(second=0, microsecond=0).isoformat()
    monkeypatch.setattr('nottle_ai.bookings.extract_details', lambda *args: {
        'name': 'Alex', 'request': 'Gutter cleaning', 'address': 'Perth', 'start': start, 'sms_consent': True})
    sent, events = [], []
    monkeypatch.setattr(service, 'sms', lambda job, phone, body: sent.append((job, phone, body)) or f'SM{job}')
    monkeypatch.setattr(service, 'calendar', lambda row, details, business: events.append(row['id']) or 'event1')
    service.capture(call_id, business, '+61400000003')
    service.tick()
    service.tick()
    with db.connect() as conn:
        code = conn.execute('SELECT id FROM booking_requests').fetchone()['id']
    return settings, db, service, code, sent, events, business, call_id


def reply(code, action='JA', **extra):
    return {'From': '+61400000002', 'Body': f'{action} {code}', 'MessageSid': 'SMinbound', **extra}


def drain(service):
    for _ in range(10):
        if not service.tick():
            break


def test_no_action_without_owner_reply(setup):
    _, db, service, code, sent, events, *_ = setup
    drain(service)
    assert len(sent) == 1 and sent[0][1] == '+61400000002'
    assert not events
    with db.connect() as conn:
        assert conn.execute('SELECT status FROM booking_requests').fetchone()['status'] == 'pending'


def test_yes_calendar_then_customer_and_duplicate_safe(setup):
    _, db, service, code, sent, events, *_ = setup
    assert 'gespeichert' in service.decide(reply(code))
    assert not events and len(sent) == 1
    drain(service)
    assert events == [code]
    assert 'confirmed' in sent[1][2] and sent[1][1] == '+61400000003'
    service.decide(reply(code, 'NEIN', MessageSid='SManother'))
    service.decide(reply(code))
    drain(service)
    assert len(events) == 1 and len(sent) == 3


def test_no_sends_polite_decline_without_calendar(setup):
    _, _, service, code, sent, events, *_ = setup
    service.decide(reply(code, 'NEIN'))
    drain(service)
    assert not events
    assert 'unable to accept' in sent[1][2]
    assert 'Thank' in sent[1][2] or 'thank' in sent[1][2]


def test_missing_date_or_calendar_remains_pending(setup):
    settings, db, service, code, *_ = setup
    with db.connect() as conn:
        conn.execute('UPDATE booking_requests SET start=NULL')
    assert 'konkreten' in service.decide(reply(code))
    service.settings = replace(settings, google_refresh_token='')
    assert 'noch nicht verbunden' in service.decide(reply(code))
    with db.connect() as conn:
        assert conn.execute('SELECT status FROM booking_requests').fetchone()['status'] == 'pending'


def test_owner_can_provide_date_and_duration(setup):
    _, db, service, code, *_ = setup
    target = datetime.now(ZoneInfo('Australia/Perth')) + timedelta(days=5)
    message = f'JA {code} {target:%d.%m.%Y} 14:30 90'
    assert 'gespeichert' in service.decide(reply(code, Body=message))
    with db.connect() as conn:
        row = conn.execute('SELECT * FROM booking_requests').fetchone()
        assert row['duration'] == 90 and '14:30:00+08:00' in row['start']


def test_wrong_owner_and_ambiguous_commands_do_not_approve(setup):
    _, db, service, code, *_ = setup
    service.decide(reply(code, From='+61400000099'))
    service.decide(reply(code, Body='JA'))
    with db.connect() as conn:
        assert conn.execute('SELECT status FROM booking_requests').fetchone()['status'] == 'pending'


def test_calendar_failure_never_confirms_customer(setup, monkeypatch):
    _, db, service, code, sent, events, *_ = setup
    def fail(*args):
        raise TimeoutError()
    monkeypatch.setattr(service, 'calendar', fail)
    service.decide(reply(code))
    service.tick()
    assert len(sent) == 1
    with db.connect() as conn:
        assert conn.execute("SELECT status FROM booking_jobs WHERE kind='calendar'").fetchone()['status'] == 'pending'


def test_no_customer_sms_without_optin(setup):
    _, db, service, code, sent, *_ = setup
    with db.connect() as conn:
        conn.execute("UPDATE booking_requests SET details=?", (json.dumps({'sms_consent': False}),))
    service.decide(reply(code, 'NEIN'))
    drain(service)
    assert all(phone == '+61400000002' for _, phone, _ in sent)
    assert 'Bitte Kunden kontaktieren' in sent[-1][2]


def test_tenant_and_duplicate_capture_isolation(setup):
    _, db, service, code, sent, events, business, call_id = setup
    service.capture(call_id, business, '+61400000003')
    service.capture(call_id, {**business, 'is_system_default': 0}, '+61400000004')
    with db.connect() as conn:
        assert conn.execute('SELECT COUNT(*) FROM booking_requests').fetchone()[0] == 1
    drain(service)
    assert len(sent) == 1


def test_restart_and_delivery_callback(setup):
    _, db, service, code, sent, *_ = setup
    with db.connect() as conn:
        conn.execute("UPDATE booking_jobs SET status='sending' WHERE kind='owner_request'")
    service.recover()
    drain(service)
    assert len(sent) == 1  # uncertain SMS is not duplicated
    service.delivery_status(sent[0][0], {'MessageSid': f'SM{sent[0][0]}', 'MessageStatus': 'delivered'})
    service.delivery_status(sent[0][0], {'MessageSid': f'SM{sent[0][0]}', 'MessageStatus': 'sent'})
    with db.connect() as conn:
        assert conn.execute("SELECT status FROM booking_jobs WHERE kind='owner_request'").fetchone()['status'] == 'delivered'


def signed(settings, path, data):
    canonical = settings.public_base_url + path + ''.join(k + data[k] for k in sorted(data))
    signature = base64.b64encode(hmac.new(settings.twilio_auth_token.encode(), canonical.encode(), hashlib.sha1).digest()).decode()
    return {'X-Twilio-Signature': signature}


def test_webhook_signature_owner_and_destination(setup):
    settings, db, service, code, *_ = setup
    app = create_app(settings)
    client = TestClient(app)  # No background worker for this route-only test.
    data = {**reply(code, 'NEIN'), 'AccountSid': settings.twilio_account_sid, 'To': settings.twilio_messaging_from}
    assert client.post('/sms/incoming', data=data).status_code == 403
    wrong = {**data, 'From': '+61400000099'}
    assert client.post('/sms/incoming', data=wrong, headers=signed(settings, '/sms/incoming', wrong)).text == '<Response/>'
    response = client.post('/sms/incoming', data=data, headers=signed(settings, '/sms/incoming', data))
    assert response.status_code == 200 and 'gespeichert' in response.text
    with db.connect() as conn:
        assert conn.execute('SELECT status FROM booking_requests').fetchone()['status'] == 'declined'


def test_google_event_id_is_stable_on_retry(setup, monkeypatch):
    from urllib.error import HTTPError
    settings, db, service, code, _, _, business, _ = setup
    service.decide(reply(code))
    with db.connect() as conn:
        row = dict(conn.execute('SELECT * FROM booking_requests').fetchone())
    events = {}
    def fake_request(url, data=None, headers=None):
        if url.endswith('/token'):
            return {'access_token': 'test-access'}
        if data:
            body = json.loads(data)
            assert body['start']['timeZone'] == 'Australia/Perth'
            events[body['id']] = body
            return body
        event_id = url.rsplit('/', 1)[-1]
        if event_id not in events:
            raise HTTPError(url, 404, 'not found', {}, None)
        return events[event_id]
    monkeypatch.setattr('nottle_ai.bookings.request_json', fake_request)
    first = Bookings.calendar(service, row, json.loads(row['details']), business)
    second = Bookings.calendar(service, row, json.loads(row['details']), business)
    assert first == second and len(events) == 1
