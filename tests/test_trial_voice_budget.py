from concurrent.futures import ThreadPoolExecutor
import asyncio
from dataclasses import replace
import json
import time

from nottle_ai import voice
from nottle_ai.security import sign_payload

from .conftest import register as register_account


def register(client, **kwargs):
    account = register_account(client, **kwargs)
    client.app.state.database.admin_update_business(account["business"]["id"], is_play_tester=True)
    return account


def reserve(db, business_id):
    return db.create_call(business_id=business_id, stream_sid="MS-test",
                          call_sid="CA-test", caller="Test caller", called_number="")


def test_trial_budget_survives_call_deletion_and_restart(client, app):
    account = register(client)
    db = app.state.database
    business_id = account["business"]["id"]
    call_id = reserve(db, business_id)
    assert call_id is not None
    assert db.delete_call(business_id, call_id)
    db.init()
    assert reserve(db, business_id) is None


def test_concurrent_trial_calls_reserve_only_one_slot(client, app):
    business_id = register(client)["business"]["id"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: reserve(app.state.database, business_id), range(4)))
    assert sum(result is not None for result in results) == 1


def test_global_trial_budget_and_paid_business_exemption(client, app):
    db = app.state.database
    # Exhaust the global budget without making any network calls.
    with db.connect() as conn:
        conn.execute("CREATE TABLE trial_voice_budget(id INTEGER PRIMARY KEY,calls INTEGER NOT NULL)")
        conn.execute("INSERT INTO trial_voice_budget VALUES(1,12)")
    business_id = register(client)["business"]["id"]
    assert reserve(db, business_id) is None
    db.admin_update_business(business_id, subscription_status="active", is_play_tester=False)
    assert reserve(db, business_id) is not None
    assert reserve(db, business_id) is not None


def test_ordinary_trial_account_is_unlimited_and_test_flag_can_be_removed(client, app):
    db = app.state.database
    business_id = register_account(client)["business"]["id"]
    assert reserve(db, business_id) is not None
    assert reserve(db, business_id) is not None
    db.admin_update_business(business_id, is_play_tester=True)
    assert reserve(db, business_id) is not None
    assert reserve(db, business_id) is None
    db.admin_update_business(business_id, is_play_tester=False)
    assert reserve(db, business_id) is not None


def test_test_limits_can_be_switched_off_globally(client, app):
    db = app.state.database
    business_id = register(client)["business"]["id"]
    assert reserve(db, business_id) is not None
    assert reserve(db, business_id) is None
    db.settings = replace(db.settings, play_test_limits_enabled=False)
    assert reserve(db, business_id) is not None


def test_tester_cannot_remove_own_flag(client, app):
    account = register(client)
    business_id = account["business"]["id"]
    response = client.patch("/api/business", json={"is_play_tester": False},
                            headers={"Authorization": "Bearer " + account["token"]})
    assert response.status_code == 200
    assert app.state.database.business_by_id(business_id)["is_play_tester"] == 1


def test_trial_stream_stops_at_deadline_and_replay_does_not_connect(client, app, monkeypatch):
    business_id = register(client)["business"]["id"]
    db = app.state.database
    db.admin_update_business(business_id, phone_status="active")
    settings = replace(app.state.settings, trial_voice_max_seconds=0.02)
    signed = sign_payload({"business_id": business_id, "call_sid": "CA-test",
                           "exp": int(time.time()) + 60}, settings.app_secret)

    class Phone:
        def __init__(self):
            self.first = True
            self.closed = False

        async def accept(self):
            pass

        async def close(self, code=1000):
            self.closed = True

        async def receive_text(self):
            if self.first:
                self.first = False
                return json.dumps({"event": "start", "start": {
                    "callSid": "CA-test", "streamSid": "MS-test",
                    "customParameters": {"token": signed}}})
            await asyncio.Event().wait()

    class AI:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def send(self, value):
            pass

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.Event().wait()

    connections = []

    def connect(*args, **kwargs):
        connections.append(True)
        return AI()

    monkeypatch.setattr(voice.websockets, "connect", connect)
    first = Phone()
    asyncio.run(voice.handle_media_stream(first, settings=settings, database=db))
    assert first.closed
    assert db.calls_for_business(business_id)[0]["status"] == "trial_limit_reached"
    second = Phone()
    asyncio.run(voice.handle_media_stream(second, settings=settings, database=db))
    assert second.closed
    assert len(connections) == 1


def test_exhausted_trial_is_rejected_before_answering(client, app):
    db = app.state.database
    business_id = register(client)["business"]["id"]
    db.admin_update_business(business_id, phone_status="active", phone_display="+61855550000")
    assert reserve(db, business_id) is not None
    response = client.post("/voice", data={"To": "+61855550000", "CallSid": "CA-repeat"})
    assert response.status_code == 200
    assert "<Reject/>" in response.text
    assert "<Connect>" not in response.text
