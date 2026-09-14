import os, json, asyncio, sqlite3, base64
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
import websockets

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "data" / "nottle_ai.db"
DB_PATH.parent.mkdir(exist_ok=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2.1")
OPENAI_VOICE = os.getenv("OPENAI_VOICE", "marin")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

BUSINESS_NAME = os.getenv("BUSINESS_NAME", "DN Property Projects")
BUSINESS_PHONE = os.getenv("BUSINESS_PHONE", "08 7666 3281")
BUSINESS_AREA = os.getenv("BUSINESS_AREA", "Perth, Western Australia")

GREETING = f"Hi, thanks for calling {BUSINESS_NAME}. You're speaking with our AI assistant. How can I help you today?"

SYSTEM_PROMPT = f"""
You are NOTTLE AI, the AI phone receptionist for {BUSINESS_NAME} in {BUSINESS_AREA}.
Start each call with this greeting: {GREETING}
Speak in Australian English. Be warm, professional, natural and concise.
Ask one question at a time and listen to the answer. Do not sound like a questionnaire.
Let the caller finish their whole thought, including pauses to think or find details.
Do not fill pauses with acknowledgements or move to the next question too early.
If the caller interrupts, stop and listen; respond to what they actually said.
Use information already provided; do not repeatedly ask for the same details.
Understand what property work the caller needs, then naturally gather their name,
best callback number, suburb or property address, preferred timing, and whether
they want a quote or an appointment. Confirm the callback number carefully.
If they want a quote, gather enough detail for Daniel to review and follow up.
Never invent prices, availability, licences, warranties, services or commitments.
Do not confirm a booking or promise a callback time. Explain that Daniel will
review the request and follow up to confirm pricing or scheduling.
If you do not know an answer, say so and offer to include the question for Daniel.
Do not claim to have sent a message, booked an appointment or performed an action
that you have not actually performed.
For emergencies involving immediate danger, tell the caller to contact emergency services.
Before ending, briefly summarise the request and check that the details are correct.
Thank the caller and explain that Daniel will review their request and follow up.
Keep responses short because this is a phone call.
""".strip()

app = FastAPI(title="NOTTLE AI")

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS calls(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stream_sid TEXT,
            call_sid TEXT,
            caller TEXT,
            created_at TEXT,
            status TEXT DEFAULT 'in_progress',
            transcript TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            is_lead INTEGER DEFAULT 1,
            booking_requested INTEGER DEFAULT 0
        )""")
init_db()

@app.get("/api/health")
def health():
    return {"ok": bool(OPENAI_API_KEY), "phone": BUSINESS_PHONE, "model": OPENAI_REALTIME_MODEL}

@app.get("/api/calls")
def calls():
    with db() as c:
        rows = c.execute("SELECT * FROM calls ORDER BY id DESC LIMIT 100").fetchall()
    return {"calls":[dict(r) for r in rows]}

@app.post("/voice")
async def voice(request: Request):
    host = request.headers.get("host", "")
    scheme = request.headers.get("x-forwarded-proto", "https")
    base = PUBLIC_BASE_URL or f"{scheme}://{host}"
    ws_base = base.replace("https://","wss://").replace("http://","ws://")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_base}/media-stream" />
  </Connect>
</Response>"""
    return Response(content=xml, media_type="application/xml")

async def send_openai_session_update(openai_ws):
    payload = {
        "type":"session.update",
        "session":{
            "type":"realtime",
            "model":OPENAI_REALTIME_MODEL,
            "instructions":SYSTEM_PROMPT,
            "output_modalities":["audio"],
            "audio":{
                "input":{
                    "format":{"type":"audio/pcmu"},
                    "turn_detection":{"type":"semantic_vad","eagerness":"low","create_response":True,"interrupt_response":True}
                },
                "output":{
                    "format":{"type":"audio/pcmu"},
                    "voice":OPENAI_VOICE
                }
            }
        }
    }
    await openai_ws.send(json.dumps(payload))

async def greet(openai_ws):
    await openai_ws.send(json.dumps({
        "type":"response.create",
        "response":{
            "instructions":SYSTEM_PROMPT + "\nBegin the phone call now. Say exactly this greeting, then wait for the caller: " + GREETING
        }
    }))

class CallPlayback:
    """Track telephone playback separately from faster-than-realtime generation."""

    def __init__(self):
        self.timestamp = 0
        self.item_id = None
        self.content_index = 0
        self.sent_ms = 0
        self.played_ms = 0
        self.start_timestamp = 0
        self.marks = {}
        self.sequence = 0
        self.interrupted_items = set()

    def audio(self, event, stream_sid):
        item_id = event.get("item_id")
        delta = event.get("delta")
        if not delta or not stream_sid or item_id in self.interrupted_items:
            return []
        if item_id != self.item_id:
            self.item_id = item_id
            self.content_index = event.get("content_index", 0)
            self.sent_ms = self.played_ms = 0
            self.start_timestamp = self.timestamp
            self.marks.clear()
        elif not self.marks:
            # Account for a gap between generated chunks without counting silence.
            self.start_timestamp = self.timestamp - self.sent_ms
        self.sent_ms += len(base64.b64decode(delta)) / 8
        self.sequence += 1
        name = f"audio-{self.sequence}"
        self.marks[name] = self.sent_ms
        return [
            {"event": "media", "streamSid": stream_sid, "media": {"payload": delta}},
            {"event": "mark", "streamSid": stream_sid, "mark": {"name": name}},
        ]

    def acknowledge(self, name):
        played = self.marks.pop(name, None)
        if played is not None:
            self.played_ms = max(self.played_ms, played)

    def interrupt(self):
        if not self.item_id or self.item_id in self.interrupted_items:
            return None
        self.interrupted_items.add(self.item_id)
        if not self.marks:
            return None
        # Twilio timestamps estimate playback; marks confirm completed chunks.
        elapsed = max(self.played_ms, self.timestamp - self.start_timestamp, 0)
        truncation = {
            "type": "conversation.item.truncate",
            "item_id": self.item_id,
            "content_index": self.content_index,
            "audio_end_ms": int(min(elapsed, self.sent_ms)),
        }
        # Late mark acknowledgements after clear must not affect the next turn.
        self.marks.clear()
        return truncation


@app.websocket("/media-stream")
async def media_stream(ws: WebSocket):
    await ws.accept()
    if not OPENAI_API_KEY:
        await ws.close(code=1011)
        return

    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    openai_url = f"wss://api.openai.com/v1/realtime?model={OPENAI_REALTIME_MODEL}"
    stream_sid = None
    call_sid = None
    call_row_id = None
    transcript_parts = []
    playback = CallPlayback()

    try:
        async with websockets.connect(openai_url, additional_headers=headers, max_size=None) as oai:
            await send_openai_session_update(oai)

            async def twilio_to_openai():
                nonlocal stream_sid, call_sid, call_row_id
                while True:
                    raw = await ws.receive_text()
                    msg = json.loads(raw)
                    event = msg.get("event")
                    if event == "start":
                        start = msg.get("start", {})
                        stream_sid = start.get("streamSid") or msg.get("streamSid")
                        call_sid = start.get("callSid")
                        caller = (start.get("customParameters") or {}).get("From","Unknown caller")
                        with db() as c:
                            cur = c.execute(
                                "INSERT INTO calls(stream_sid,call_sid,caller,created_at) VALUES(?,?,?,?)",
                                (stream_sid,call_sid,caller,datetime.now(timezone.utc).isoformat())
                            )
                            call_row_id = cur.lastrowid
                        await greet(oai)
                    elif event == "media":
                        playback.timestamp = int(msg.get("media", {}).get("timestamp", playback.timestamp))
                        payload = msg.get("media",{}).get("payload")
                        if payload:
                            await oai.send(json.dumps({"type":"input_audio_buffer.append","audio":payload}))
                    elif event == "mark":
                        playback.acknowledge(msg.get("mark", {}).get("name"))
                    elif event == "stop":
                        break

            async def openai_to_twilio():
                nonlocal transcript_parts
                async for raw in oai:
                    event = json.loads(raw)
                    t = event.get("type","")
                    if t in ("response.output_audio.delta","response.audio.delta"):
                        for message in playback.audio(event, stream_sid):
                            await ws.send_text(json.dumps(message))
                    elif t == "input_audio_buffer.speech_started":
                        truncation = playback.interrupt()
                        if stream_sid:
                            await ws.send_text(json.dumps({"event":"clear", "streamSid":stream_sid}))
                        if truncation:
                            await oai.send(json.dumps(truncation))
                    elif t in ("response.output_audio_transcript.delta","response.audio_transcript.delta"):
                        d = event.get("delta")
                        if d:
                            transcript_parts.append("AI: "+d)
                    elif t in ("conversation.item.input_audio_transcription.completed","input_audio_transcription.completed"):
                        tr = event.get("transcript")
                        if tr:
                            transcript_parts.append("Caller: "+tr)
                    elif t == "error":
                        print("OpenAI realtime error:", event)

            tasks = [
                asyncio.create_task(twilio_to_openai()),
                asyncio.create_task(openai_to_twilio())
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for p in pending:
                p.cancel()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        print("media-stream error:", repr(e))
    finally:
        if call_row_id:
            transcript = "\n".join(transcript_parts)[-20000:]
            lower = transcript.lower()
            booking = 1 if any(k in lower for k in ["book","appointment","when can","schedule","available"]) else 0
            summary = "Call completed. Review transcript." if transcript else "Call completed."
            with db() as c:
                c.execute(
                    "UPDATE calls SET status='completed', transcript=?, summary=?, booking_requested=? WHERE id=?",
                    (transcript, summary, booking, call_row_id)
                )

@app.get("/")
def root():
    return HTMLResponse((APP_DIR/"static"/"index.html").read_text(encoding="utf-8"))

app.mount("/", StaticFiles(directory=APP_DIR/"static", html=True), name="static")
