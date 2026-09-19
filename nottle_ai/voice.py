from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import websockets
from fastapi import WebSocket, WebSocketDisconnect

from .config import Settings
from .database import Database
from .security import verify_payload


logger = logging.getLogger("nottle_ai.voice")


def _clean(value: Any, limit: int = 1500) -> str:
    return " ".join(str(value or "").split())[:limit]


def build_greeting(business: dict[str, Any]) -> str:
    business_name = _clean(business.get("name"), 120) or "the business"
    assistant_name = _clean(business.get("assistant_name"), 40) or "Nottle"
    custom = _clean(business.get("greeting"), 240)
    opening = (
        f"Hi, thanks for calling {business_name}. I'm {assistant_name}, an AI assistant. "
        "This call will be transcribed so the team can follow up."
    )
    return f"{opening} {custom}" if custom else f"{opening} How can I help you today?"


def build_system_prompt(business: dict[str, Any]) -> str:
    name = _clean(business.get("name"), 120)
    area = _clean(business.get("area"), 160)
    industry = _clean(business.get("industry"), 120)
    services = _clean(business.get("services"), 1200)
    hours = _clean(business.get("business_hours"), 500)
    extra = _clean(business.get("extra_instructions"), 1200)
    greeting = build_greeting(business)
    assistant_name = _clean(business.get("assistant_name"), 40) or "Nottle"
    return f"""
You are {assistant_name}, the AI phone receptionist for {name}.

BUSINESS CONTEXT
- Service area: {area or 'Not specified'}
- Industry: {industry or 'General small business'}
- Services: {services or 'Ask the caller what help they need'}
- Business hours: {hours or 'Availability must be confirmed by the business'}
- Owner instructions: {extra or 'No additional instructions'}

CALL RULES
1. Begin once with exactly this greeting: {greeting}
2. Speak in natural Australian English. Be warm, calm, professional and concise.
3. Ask only one question at a time. Never sound like a questionnaire.
4. Let the caller finish their complete thought, including pauses while thinking.
5. Do not fill a pause with acknowledgements and do not rush to the next question.
6. If the caller interrupts, immediately stop speaking and listen.
7. Use details already given. Never ask for the same information twice.
8. Understand the request, then naturally collect the caller's name, best callback
   number, location, preferred timing and whether they want a quote or appointment.
9. Repeat important names, addresses and phone numbers once for confirmation.
10. Never invent prices, availability, licences, warranties, services or promises.
11. Never claim a booking or action is confirmed unless a real tool confirmed it.
12. Say the business will review the request and follow up to confirm next steps.
13. If you do not know something, say so and include the question in the enquiry.
14. For immediate danger, tell the caller to contact emergency services.
15. Before ending, give a short summary and ask whether the details are correct.
16. Keep each reply short because this is a telephone call.
""".strip()


def turn_detection_for(business: dict[str, Any]) -> dict[str, Any]:
    pace = str(business.get("conversation_pace") or "patient")
    eagerness = {"patient": "low", "balanced": "medium", "fast": "high"}.get(
        pace, "low"
    )
    return {
        "type": "semantic_vad",
        "eagerness": eagerness,
        "create_response": True,
        "interrupt_response": True,
    }


async def configure_openai_session(
    openai_ws: Any, settings: Settings, business: dict[str, Any]
) -> None:
    transcription: dict[str, Any] = {
        "model": settings.openai_transcribe_model,
        "languages": ["en"],
        "delay": "medium",
        "prompt": f"A customer phone call to {_clean(business.get('name'), 120)}.",
    }
    service_keywords = [
        item.strip()[:80]
        for item in str(business.get("services") or "").replace(";", ",").split(",")
        if item.strip()
    ][:20]
    if service_keywords:
        transcription["keywords"] = service_keywords

    payload = {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": settings.openai_realtime_model,
            "instructions": build_system_prompt(business),
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {"type": "audio/pcmu"},
                    "transcription": transcription,
                    "turn_detection": turn_detection_for(business),
                },
                "output": {
                    "format": {"type": "audio/pcmu"},
                    "voice": business.get("voice") or settings.openai_voice,
                },
            },
        },
    }
    await openai_ws.send(json.dumps(payload))


async def greet(openai_ws: Any, business: dict[str, Any]) -> None:
    await openai_ws.send(
        json.dumps(
            {
                "type": "response.create",
                "response": {
                    "instructions": (
                        "Begin the call now. Say exactly the following greeting, then stop "
                        "and wait for the caller: " + build_greeting(business)
                    )
                },
            }
        )
    )


class CallPlayback:
    """Track telephone playback separately from faster-than-realtime generation."""

    def __init__(self) -> None:
        self.timestamp = 0
        self.item_id: str | None = None
        self.content_index = 0
        self.sent_ms = 0.0
        self.played_ms = 0.0
        self.start_timestamp = 0.0
        self.marks: dict[str, float] = {}
        self.sequence = 0
        self.interrupted_items: set[str] = set()

    def audio(self, event: dict[str, Any], stream_sid: str | None) -> list[dict[str, Any]]:
        item_id = event.get("item_id")
        delta = event.get("delta")
        if not delta or not stream_sid or item_id in self.interrupted_items:
            return []
        if item_id != self.item_id:
            self.item_id = item_id
            self.content_index = int(event.get("content_index", 0))
            self.sent_ms = self.played_ms = 0
            self.start_timestamp = self.timestamp
            self.marks.clear()
        elif not self.marks:
            self.start_timestamp = self.timestamp - self.sent_ms
        try:
            self.sent_ms += len(base64.b64decode(delta)) / 8
        except (ValueError, TypeError):
            return []
        self.sequence += 1
        name = f"audio-{self.sequence}"
        self.marks[name] = self.sent_ms
        return [
            {"event": "media", "streamSid": stream_sid, "media": {"payload": delta}},
            {"event": "mark", "streamSid": stream_sid, "mark": {"name": name}},
        ]

    def acknowledge(self, name: str | None) -> None:
        played = self.marks.pop(name or "", None)
        if played is not None:
            self.played_ms = max(self.played_ms, played)

    def interrupt(self) -> dict[str, Any] | None:
        if not self.item_id or self.item_id in self.interrupted_items:
            return None
        self.interrupted_items.add(self.item_id)
        if not self.marks:
            return None
        elapsed = max(self.played_ms, self.timestamp - self.start_timestamp, 0)
        truncation = {
            "type": "conversation.item.truncate",
            "item_id": self.item_id,
            "content_index": self.content_index,
            "audio_end_ms": int(min(elapsed, self.sent_ms)),
        }
        self.marks.clear()
        return truncation


@dataclass
class Transcript:
    turns: list[tuple[str, str]] = field(default_factory=list)
    ai_deltas: dict[str, str] = field(default_factory=dict)

    def caller(self, text: str) -> None:
        cleaned = _clean(text, 5000)
        if cleaned:
            self.turns.append(("Caller", cleaned))

    def ai_delta(self, item_id: str, delta: str) -> None:
        if delta:
            self.ai_deltas[item_id] = self.ai_deltas.get(item_id, "") + delta

    def ai_done(self, item_id: str, transcript: str = "") -> None:
        text = _clean(transcript or self.ai_deltas.pop(item_id, ""), 5000)
        if text:
            self.turns.append(("AI", text))

    def render(self) -> str:
        for item_id in list(self.ai_deltas):
            self.ai_done(item_id)
        return "\n".join(f"{speaker}: {text}" for speaker, text in self.turns)

    def summary(self) -> tuple[str, bool]:
        caller_turns = [text for speaker, text in self.turns if speaker == "Caller"]
        all_text = " ".join(caller_turns)
        lower = all_text.lower()
        booking = any(
            phrase in lower
            for phrase in ("book", "appointment", "schedule", "available", "come out", "quote")
        )
        if not caller_turns:
            return "Call ended before an enquiry was captured.", False
        request = caller_turns[0]
        if len(request) > 260:
            request = request[:257].rstrip() + "…"
        prefix = "Booking or quote request" if booking else "New customer enquiry"
        return f"{prefix}: {request}", booking


async def _receive_start(ws: WebSocket) -> dict[str, Any] | None:
    while True:
        raw = await ws.receive_text()
        message = json.loads(raw)
        event = message.get("event")
        if event == "start":
            return message
        if event == "stop":
            return None


async def handle_media_stream(
    ws: WebSocket, *, settings: Settings, database: Database
) -> None:
    await ws.accept()
    call_id: int | None = None
    started = time.monotonic()
    transcript = Transcript()
    final_status = "completed"
    error_message = ""

    try:
        start_message = await _receive_start(ws)
        if not start_message:
            await ws.close(code=1000)
            return
        start = start_message.get("start") or {}
        custom = start.get("customParameters") or {}
        stream_sid = start.get("streamSid") or start_message.get("streamSid")
        call_sid = start.get("callSid") or custom.get("call_sid") or ""
        signed = custom.get("token") or ""
        payload = verify_payload(signed, settings.app_secret)
        if not payload or int(payload.get("business_id", 0)) < 1:
            await ws.close(code=1008)
            return
        if payload.get("call_sid") and call_sid and payload["call_sid"] != call_sid:
            await ws.close(code=1008)
            return
        business = database.business_by_id(int(payload["business_id"]))
        if not business or business.get("phone_status") != "active":
            await ws.close(code=1008)
            return
        if not settings.openai_api_key:
            await ws.close(code=1011)
            return

        caller = custom.get("from") or "Unknown caller"
        called_number = custom.get("to") or business.get("phone_display") or ""
        call_id = database.create_call(
            business_id=int(business["id"]),
            stream_sid=stream_sid or "",
            call_sid=call_sid,
            caller=caller,
            called_number=called_number,
        )

        headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
        openai_url = (
            "wss://api.openai.com/v1/realtime?model=" + settings.openai_realtime_model
        )
        playback = CallPlayback()

        async with websockets.connect(
            openai_url,
            additional_headers=headers,
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
        ) as openai_ws:
            await configure_openai_session(openai_ws, settings, business)
            await greet(openai_ws, business)

            async def twilio_to_openai() -> None:
                while True:
                    raw = await ws.receive_text()
                    message = json.loads(raw)
                    event = message.get("event")
                    if event == "media":
                        media = message.get("media") or {}
                        playback.timestamp = int(media.get("timestamp", playback.timestamp))
                        audio = media.get("payload")
                        if audio:
                            await openai_ws.send(
                                json.dumps(
                                    {"type": "input_audio_buffer.append", "audio": audio}
                                )
                            )
                    elif event == "mark":
                        playback.acknowledge((message.get("mark") or {}).get("name"))
                    elif event == "stop":
                        return

            async def openai_to_twilio() -> None:
                async for raw in openai_ws:
                    event = json.loads(raw)
                    event_type = event.get("type", "")
                    if event_type in (
                        "response.output_audio.delta",
                        "response.audio.delta",
                    ):
                        for outgoing in playback.audio(event, stream_sid):
                            await ws.send_text(json.dumps(outgoing))
                    elif event_type == "input_audio_buffer.speech_started":
                        truncation = playback.interrupt()
                        if stream_sid:
                            await ws.send_text(
                                json.dumps({"event": "clear", "streamSid": stream_sid})
                            )
                        if truncation:
                            await openai_ws.send(json.dumps(truncation))
                    elif event_type in (
                        "response.output_audio_transcript.delta",
                        "response.audio_transcript.delta",
                    ):
                        transcript.ai_delta(
                            str(event.get("item_id") or event.get("response_id") or "ai"),
                            str(event.get("delta") or ""),
                        )
                    elif event_type in (
                        "response.output_audio_transcript.done",
                        "response.audio_transcript.done",
                    ):
                        transcript.ai_done(
                            str(event.get("item_id") or event.get("response_id") or "ai"),
                            str(event.get("transcript") or ""),
                        )
                    elif event_type in (
                        "conversation.item.input_audio_transcription.completed",
                        "input_audio_transcription.completed",
                    ):
                        transcript.caller(str(event.get("transcript") or ""))
                    elif event_type == "error":
                        logger.warning("OpenAI Realtime error: %s", event)

            phone_task = asyncio.create_task(twilio_to_openai())
            ai_task = asyncio.create_task(openai_to_twilio())
            done, pending = await asyncio.wait(
                (phone_task, ai_task), return_when=asyncio.FIRST_COMPLETED
            )
            if phone_task in done and ai_task in pending:
                try:
                    await asyncio.wait_for(asyncio.shield(ai_task), timeout=0.8)
                except (asyncio.TimeoutError, WebSocketDisconnect):
                    pass
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, return_exceptions=True)
            await asyncio.gather(*pending, return_exceptions=True)

    except WebSocketDisconnect:
        pass
    except Exception as exc:  # keep the telephony webhook alive on upstream failures
        final_status = "error"
        error_message = type(exc).__name__
        logger.exception("Media stream failed")
    finally:
        if call_id:
            rendered = transcript.render()
            summary, booking = transcript.summary()
            database.finish_call(
                call_id,
                status=final_status,
                transcript=rendered,
                summary=summary,
                booking_requested=booking,
                duration_seconds=int(time.monotonic() - started),
                error_message=error_message,
            )
