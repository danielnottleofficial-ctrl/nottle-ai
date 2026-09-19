from __future__ import annotations

import asyncio
import base64
import json
import time

from nottle_ai.security import (
    hash_password,
    normalize_phone,
    sign_payload,
    verify_password,
    verify_payload,
)
from nottle_ai.voice import CallPlayback, Transcript, configure_openai_session, turn_detection_for


class FakeSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send(self, value: str) -> None:
        self.messages.append(json.loads(value))


def test_passwords_signed_tokens_and_phone_normalisation() -> None:
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded)
    assert not verify_password("wrong", encoded)
    assert normalize_phone("08 7666 3281") == "+61876663281"

    secret = "s" * 40
    signed = sign_payload({"business_id": 7, "exp": int(time.time()) + 60}, secret)
    assert verify_payload(signed, secret)["business_id"] == 7
    assert verify_payload(signed + "tampered", secret) is None


def test_patient_turn_detection_and_realtime_session(settings) -> None:
    business = {
        "name": "Test Business",
        "conversation_pace": "patient",
        "services": "Electrical, maintenance",
        "voice": "marin",
    }
    assert turn_detection_for(business) == {
        "type": "semantic_vad",
        "eagerness": "low",
        "create_response": True,
        "interrupt_response": True,
    }

    socket = FakeSocket()
    asyncio.run(configure_openai_session(socket, settings, business))
    session = socket.messages[0]["session"]
    assert session["model"] == "gpt-realtime-2.1"
    assert session["audio"]["input"]["format"] == {"type": "audio/pcmu"}
    assert session["audio"]["input"]["turn_detection"]["eagerness"] == "low"
    assert session["audio"]["input"]["transcription"]["model"] == "gpt-live-transcribe"


def test_playback_truncation_and_transcript_summary() -> None:
    playback = CallPlayback()
    playback.timestamp = 1000
    audio = base64.b64encode(b"x" * 800).decode()
    messages = playback.audio({"item_id": "item-1", "delta": audio}, "MS1")
    assert [message["event"] for message in messages] == ["media", "mark"]
    playback.timestamp = 1050
    truncation = playback.interrupt()
    assert truncation["type"] == "conversation.item.truncate"
    assert truncation["audio_end_ms"] == 50

    transcript = Transcript()
    transcript.caller("I'd like to book a quote for garden maintenance")
    transcript.ai_delta("assistant-1", "Certainly. ")
    transcript.ai_done("assistant-1", "Certainly. What suburb are you in?")
    summary, booking = transcript.summary()
    assert booking is True
    assert summary.startswith("Booking or quote request:")
    assert "Caller:" in transcript.render()
