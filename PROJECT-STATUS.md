# NOTTLE AI release status

Updated 27 October 2026 (Australia/Perth).

- Android version 1.1, versionCode 4, package com.nottleai.app.
- Signed AAB accepted in the existing closed Alpha test; update and Data safety changes submitted for Google review.
- Business-calendar service-account read/create/read-back/cleanup test passed.
- App mode enabled for controlled owner-device testing; calendar creation requires explicit authenticated owner approval.
- Automatic Twilio booking SMS remains disabled; native SMS composer requires the owner to send the message.
- Sixteen booking/app tests pass. An older full-suite run had 33 passes and one pre-existing VAD expectation failure.
- Real-device foreground/background/cold-start push, SMS composer, approve/decline and resulting calendar checks remain outstanding.
- Public production access remains gated by Google's closed-test requirement.
- Runtime credentials and private operational/account notes are managed separately and must never be committed.
- This snapshot is a source backup. It does not change the production deployment or main branch.
