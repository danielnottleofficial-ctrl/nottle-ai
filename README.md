# NOTTLE AI — Twilio Voice App

Complete MVP for DN Property Projects.

Included:
- Installable mobile-friendly web app dashboard
- Twilio incoming-call webhook: POST /voice
- Twilio Media Streams WebSocket: /media-stream
- OpenAI Realtime voice bridge
- SQLite call history
- Render deployment configuration

Configured business number:
08 7666 3281

Before a live call can be answered:
1. Deploy this project to a public HTTPS host.
2. Add OPENAI_API_KEY as a secret environment variable.
3. Set PUBLIC_BASE_URL to the deployed HTTPS URL.
4. In Twilio set the incoming-call webhook to:
   https://YOUR-APP.onrender.com/voice
   Method: POST

The AI prompt is configured to identify itself as an AI assistant.
