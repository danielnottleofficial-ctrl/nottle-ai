# App approval workflow — implementation checkpoint, not deployed

The app now supports Firebase push registration, opening the associated call,
confirm/decline controls, and native ACTION_SENDTO SMS drafts using the user's SIM.
Only explicit authenticated confirmation queues a Google Calendar event. Duplicate
confirmations cannot create multiple entries. Decline does not write a calendar.
Automatic Twilio SMS jobs are skipped in app mode. SMS drafts are never marked sent.

Enable APP_APPROVAL_ENABLED=true only after the deployment and device tests below.
BOOKING_APPROVAL_ENABLED remains false. The app workflow currently targets the
configured default business, excluding Play testers. Push notifications contain a
private generic alert; customer data is read after authenticated app access.

Required deployment configuration:
- Existing FIREBASE_SERVICE_ACCOUNT_JSON in Render; never commit this secret.
- GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN, GOOGLE_CALENDAR_ID.
  Google account authorization is not complete. Calendar confirm is disabled without it.
- Persistent SQLite, one worker process, correctly owned default business account.
- android/app/google-services.json from existing Firebase project nottle-ai,
  package com.nottleai.app (available locally, intentionally ignored by git).
- npm ci && npm run android:sync; build with Java 21 + Android SDK and the original
  Play upload signing key. VersionCode 3 (Play currently uses 2), versionName 1.1.

Validation 2026-10-26:
- 16 booking/app tests pass; JS syntax and ruff on changed backend modules pass.
- Entire test suite: 33 pass, one pre-existing VAD expectation failure (also proven
  on original main during earlier work).
- Native web bundle and Capacitor sync succeeded.
- Android build repaired with explicit proxy, Java 21, SDK 36; signed AAB/APK built successfully.
- Signed AAB/APK version 3 built; AAB signature verified. No live device end-to-end test yet.
- Device checks still required: notifications in foreground/background/cold launch,
  logout and account switching, permission denial, SMS composer, calendar failure
  and successful confirmed event. Never claim ready before these pass.

Continuity: earlier Firebase-only code was found in another local checkout,
commit 4d10d51 at /workspace/scratch/1130e6a29681/nottle-ai. It was not deployed.
Current app-approval changes extend the SMS approval branch with a no-Twilio app mode.

Dedicated Google Calendar created in Perth timezone: DN Property Projects – Termine.
Calendar ID: c9686ad6adfc2d1561e60776ca5bf25ddc1e036b7cff53e034669b93309185e3@group.calendar.google.com
Sharing with firebase-adminsdk-fbsvc@nottle-ai.iam.gserviceaccount.com is prepared, not submitted.
Requires user confirmation of new calendar write access. Then set GOOGLE_USE_SERVICE_ACCOUNT=true
and GOOGLE_CALENDAR_ID to the above ID. This uses existing Firebase credentials on Render.
