# NOTTLE AI

NOTTLE AI is an Australian AI receptionist platform for small businesses. It
answers Twilio calls through OpenAI Realtime, captures enquiries and presents
call summaries, transcripts and assistant settings in a secure customer app.

## Included

- Email registration, login, password reset, sessions and account deletion
- Multi-business customer dashboard with calls, leads and booking requests
- Self-service assistant profile, voice, greeting and listening-pace settings
- Admin account activation and phone-number assignment
- Twilio webhook validation and tenant-safe Media Streams routing
- OpenAI Realtime audio bridge with semantic VAD and patient interruption handling
- Call transcripts, summaries, data export and privacy controls
- Responsive web/PWA UI and a Capacitor Android app
- Privacy Policy, Terms, support and deletion-request pages
- Render deployment blueprint with persistent SQLite storage
- Play Store listing copy, data-safety notes and release assets

The configured DN Property Projects number is **08 7666 3281**.

## Local development

Requires Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn main:app --reload
```

Environment variables are not loaded from `.env` automatically. Export them in
your shell, use your process manager, or install a local dotenv runner. The app
is available at `http://localhost:8000`.

Run checks with:

```bash
ruff check .
pytest
```

## Production deployment

Create a Render Blueprint from `render.yaml` and provide these secret values:

- `OPENAI_API_KEY`
- `TWILIO_AUTH_TOKEN`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD` (at least 10 characters)
- `SMTP_USERNAME`
- `SMTP_PASSWORD`

Render generates `APP_SECRET` and mounts persistent storage at `/var/data`.
Keep one web process while using SQLite. The production health check also
verifies that password-reset email is configured before the service is marked
ready.

In Twilio, configure the incoming-number voice webhook as:

```text
POST https://nottle-ai.onrender.com/voice
```

The Twilio number must match the active number on the corresponding NOTTLE AI
business account. The default account normalises `08 7666 3281` to
`+61 8 7666 3281` for routing.

## Android

The native shell is in `android/` and uses package ID `com.nottleai.app`. It
loads the bundled interface and connects securely to
`https://nottle-ai.onrender.com` for customer data.

Build a signed bundle with the instructions in `play-store/RELEASE.md`. Never
commit an upload keystore or its password.

## Privacy and disclosure

The mandatory greeting identifies the receptionist as AI and advises callers
that the call is transcribed. The dashboard provides call deletion, full account
deletion and JSON export. Before public launch, confirm the policies and your
call-recording/transcription obligations with an Australian legal professional.

## Android call notifications

The Android app registers an FCM device token against its authenticated session.
After each persisted call, an SQLite outbox queues a private notification for
that business owner's signed-in devices. The background worker retries temporary
failures. Logout, password reset, account deletion and token reassignment revoke
associated deliveries. Notification taps open the call in the authenticated app.
Caller details use the recorded caller words, with full details in the call view.

Activation required:
- Firebase project `nottle-ai`, Android package `com.nottleai.app`.
- Download the Android client configuration to `android/app/google-services.json`
  (excluded from git), then run `npm run android:sync`.
- Configure a dedicated service account with Cloud Messaging send permission.
  Store its JSON ONLY as the Render secret `FIREBASE_SERVICE_ACCOUNT_JSON`, or
  use `GOOGLE_APPLICATION_CREDENTIALS` pointing to a private mounted secret.
  Never commit server credentials or bundle them in the app.
- Build/sign version 1.1 (code 2) with the existing upload key, distribute through
  the existing Play testing track, then permit notifications on the handset.
- Verify with a real call while the updated app is closed.

Until a server credential is configured, the app reports activation pending.
No Firebase billing upgrade, Analytics or extra cloud compute is required.
Run the focused tests with `python -m pytest tests/test_push.py -q`.
