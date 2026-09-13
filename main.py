import os, json, asyncio, sqlite3
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

SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", f"""
You are NOTTLE AI, the AI phone receptionist for {BUSINESS_NAME} in {BUSINESS_AREA}.
At the start of every call, clearly identify yourself as an AI assistant.
Be warm, concise, professional and natural. Use Australian English.
Your job is to:
1. Find out the caller's name and best callback number.
2. Understand what property work they need.
3. Ask the suburb/location.
4. Ask when they would like the work done.
5. If they want a quote, gather enough detail for Daniel to follow up.
6. Never invent prices, availability, licences, warranties, or commitments.
7. If the caller asks for an exact quote, explain that Daniel will review the details and follow up.
8. For emergencies involving immediate danger, tell them to contact emergency services.
9. Before ending, briefly confirm the captured details.
Keep responses short because this is a phone call.
""").strip()

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
                    "turn_detection":{"type":"server_vad","create_response":True,"interrupt_response":True}
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
            "instructions":f"Begin the phone call now. Say you are NOTTLE AI, the AI assistant for {BUSINESS_NAME}, and ask how you can help."
        }
    }))

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
                        payload = msg.get("media",{}).get("payload")
                        if payload:
                            await oai.send(json.dumps({"type":"input_audio_buffer.append","audio":payload}))
                    elif event == "stop":
                        break

            async def openai_to_twilio():
                nonlocal transcript_parts
                async for raw in oai:
                    event = json.loads(raw)
                    t = event.get("type","")
                    if t in ("response.output_audio.delta","response.audio.delta"):
                        delta = event.get("delta")
                        if delta and stream_sid:
                            await ws.send_text(json.dumps({
                                "event":"media",
                                "streamSid":stream_sid,
                                "media":{"payload":delta}
                            }))
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
