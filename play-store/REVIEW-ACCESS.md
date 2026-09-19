# Google Play review access

NOTTLE AI requires sign-in. Google must receive working credentials that remain valid for the entire review.

## Text for Play Console

Use this in **Policy and programs > App content > App access** after creating the reviewer account on the live production server:

> Sign-in is required. Use the reviewer email and password supplied below. No one-time code, location restriction or additional approval is required. After sign-in, Overview shows the assistant status and recent calls. Use Calls to review call summaries and transcripts, Assistant to edit the business configuration, and Settings to test export and account privacy controls. Please do not delete the reviewer account.

## Credentials to enter in Play Console

- Email: create a dedicated address such as `play-review@your-domain.example`
- Password: create a unique password of at least 16 characters

Do not put the live password in this repository. Store it only in the Play Console access field and your password manager.

## Before submitting

1. Register the reviewer account against the live URL.
2. Sign in once from a separate device and confirm that it works without a one-time code.
3. Complete the Assistant setup for the review business.
4. Keep the account and password unchanged until the release is approved.
