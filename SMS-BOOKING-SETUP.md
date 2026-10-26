# SMS approval and Google Calendar

Prepared workflow for Daniel's **default business only**. Other tenants and Play
review accounts do not send messages to Daniel. Feature is off until configured.

1. Completed enquiries are saved to the persistent SQLite queue. The owner receives
   the caller's name, request, address, proposed date/time and a unique code.
2. `JA CODE` or `YES CODE` approves the displayed proposal. A different date/time
   can be supplied with `JA CODE DD.MM.YYYY HH:MM [duration in minutes]`.
   The displayed default duration is 60 minutes. Ambiguous/missing times require
   an explicit date/time. Date interpretation uses the business timezone (Perth).
3. Only an authenticated Twilio SMS from the configured owner's number, sent to
   the configured SMS number, can approve or decline. `NEIN CODE` / `NO CODE`
   sends a polite English decline. Silence leaves the request pending indefinitely.
4. On approval, Google Calendar is written first; only successful calendar writes
   allow the English customer confirmation. Google event IDs are deterministic,
   so retries do not duplicate appointments. Duplicate decisions are ignored.
5. Customer messages use the inbound AU mobile number, after the receptionist asks
   for SMS consent. Landlines, withheld numbers and declined consent require a
   personal callback; the owner is informed. Messages are transactional only.

## Deployment configuration

Use the existing Render service and persistent SQLite disk, **one worker process**.
Keep `BOOKING_APPROVAL_ENABLED=false` until credentials and callbacks are checked.

Required secret/configuration names (values must never be committed):

- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`
- `TWILIO_MESSAGING_FROM`: E.164 Twilio number with inbound AND outbound SMS support.
  Do not assume the Perth voice number can receive SMS.
- `SMS_SUMMARY_RECIPIENT`: Daniel's verified E.164 mobile number.
- `PUBLIC_BASE_URL=https://nottle-ai.onrender.com`
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`
- `GOOGLE_CALENDAR_ID`: explicitly selected owner calendar. The connected ChatGPT
  calendar is `daniel.nottle.official@gmail.com`; the deployed server needs its own
  Google OAuth authorisation, which is separate from the ChatGPT connection.
- `BOOKING_EXTRACT_MODEL=gpt-4.1-mini` (configurable)

Enable Google Calendar API and obtain an offline OAuth grant for the selected
calendar with `https://www.googleapis.com/auth/calendar.events`. Use a production
OAuth configuration; a testing consent grant may expire. Store credentials only
in Render's secrets. No Google credentials are provided by this code change.

In Twilio, set the SMS-enabled number's incoming **Messaging** webhook to:
`POST https://nottle-ai.onrender.com/sms/incoming`.
Voice remains on `/voice`. Outbound messages automatically set the signed
`/sms/status/{job_id}` delivery callback. Verify signatures are always enforced
on SMS routes, even if the voice development flag disables them.

## Operations and failure behaviour

`GET /api/admin/bookings` requires an authenticated admin and shows requests,
job states and delivery status, without provider credentials. `accepted` means
Twilio accepted a message, not that the handset received it; use `delivered`.
Customer failures notify the owner. Calendar failures retry with backoff and
never confirm the customer before success. Exhausted retries notify the owner.

An SMS network timeout has an uncertain outcome: it is marked `unknown` and is
not automatically resent (Twilio message creation is not idempotent). Check the
Twilio message log before any manual resend. A signed delivery callback can
resolve its state. Restarted calendar work retries safely; interrupted SMS work
also becomes `unknown`. There is no unattended resend tool for uncertain SMS.

Before enabling, run a real call from an authorised test mobile, then owner JA
and NEIN on separate requests. Verify actual handset delivery and the selected
Google calendar. Do not send test SMS to an unverified real customer. Also check
non-owner replies, duplicate replies, missing times and invalid signatures.

## Validation of this change

New booking tests cover pending requests, approval/rejection, duplicate replies,
calendar failure, consent, tenant isolation, timestamp overrides, restart recovery,
delivery ordering and signed webhook validation. Existing baseline has one failing
voice test (`test_patient_turn_detection_and_realtime_session`): it expects
semantic VAD but the repository uses server VAD. This was reproduced on unmodified
commit `20e3d14`; the SMS feature does not change VAD settings.
