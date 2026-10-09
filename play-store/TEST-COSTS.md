# Google Play tester call limits

Only accounts explicitly marked `is_play_tester` by an administrator receive
these limits. Ordinary customers, including ordinary trial accounts, keep their
existing behaviour. New accounts are not marked automatically.

The default allowance is one AI telephone call of at most 60 seconds per
marked business, and 12 calls total across all marked businesses. Test calls
do not send paid SMS summaries. After exhaustion, the voice webhook rejects
the call before answering. Simultaneous streams reserve quota atomically.
Deleting call history does not reset quota; the shared budget survives account
deletion. These are usage limits, not an exact AUD spending limit.

Before inviting testers, mark their accounts using the administrator dashboard
checkbox **Play tester (limited calls)**. This controls telephone calls handled
by `/voice` and `/media-stream`; it does not add an in-app voice preview endpoint.

After testing, remove the flags or set `PLAY_TEST_LIMITS_ENABLED=false` in Render.
No code removal is needed. A deployment/restart is needed for environment changes.

Optional environment settings: `TRIAL_VOICE_MAX_CALLS=1`,
`TRIAL_VOICE_MAX_SECONDS=60`, `TRIAL_VOICE_TOTAL_CALLS=12`.
The legacy TRIAL names are configuration keys; the restriction is tester-only.
