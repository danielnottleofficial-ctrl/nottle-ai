# NOTTLE AI im Google Play Store veröffentlichen

## Fertige Upload-Dateien

- Android App Bundle: `NOTTLE-AI-v1.0.aab`
- Store-Symbol: `assets/icon-512.png`
- Feature-Grafik: `assets/feature-graphic-1024x500.png`
- Vier Handy-Screenshots: `assets/phone/`
- Store-Texte: `LISTING.md`
- Datenschutz-Antworten: `DATA-SAFETY.md`
- Prüfer-Zugang: `REVIEW-ACCESS.md`
- Öffentliches Upload-Zertifikat: `upload_certificate.pem`

## 1. Produktionsdienst einschalten

Der Android-Client verbindet sich mit `https://nottle-ai.onrender.com`. Vor der Play-Einreichung muss diese Adresse erreichbar sein.

In Render müssen folgende geheimen Werte gesetzt sein:

- `OPENAI_API_KEY`
- `TWILIO_AUTH_TOKEN`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD` (mindestens 10 Zeichen)
- `SMTP_USERNAME`
- `SMTP_PASSWORD`

Render erzeugt `APP_SECRET` automatisch. Danach muss der Health-Check unter `/api/health` erfolgreich sein.

## 2. Telefonnummer verbinden

Beim aktiven Twilio-Telefonanschluss den Voice-Webhook setzen:

```text
POST https://nottle-ai.onrender.com/voice
```

Dann einen echten Testanruf durchführen. Der Assistent muss sich als KI vorstellen, die Transkription ankündigen, den Anrufer ausreden lassen und den fertigen Eintrag im Dashboard anzeigen.

## 3. Play Console ausfüllen

1. Neue App `NOTTLE AI`, Standardsprache Englisch (Australien), App, kostenlose Installation.
2. Paket-ID: `com.nottleai.app`.
3. Store-Eintrag mit `LISTING.md` und den Dateien aus `assets/` ausfüllen.
4. Datenschutzerklärung und Lösch-URL eintragen.
5. Unter App-Zugriff einen gültigen Prüfer-Login gemäß `REVIEW-ACCESS.md` hinterlegen.
6. Werbung: Nein. Zielgruppe: Erwachsene/Geschäftsnutzer. Inhaltsbewertung und Data Safety ausfüllen.
7. `NOTTLE-AI-v1.0.aab` zuerst in den internen Test hochladen.
8. Auf mindestens einem echten Android-Gerät Login, Einstellungen, Datenexport, Löschung und Darstellung prüfen.

## 4. Testpflicht und Produktion

Bei einem **persönlichen Play-Entwicklerkonto, das nach dem 13. November 2023 erstellt wurde**, verlangt Google vor dem Produktionszugang einen geschlossenen Test mit mindestens 12 dauerhaft angemeldeten Testern über mindestens 14 aufeinanderfolgende Tage. Danach in der Play Console den Produktionszugang beantragen.

Bei einem älteren oder berechtigten Organisationskonto kann dieser zusätzliche Zeitraum entfallen. Die Play Console zeigt die für das konkrete Konto geltenden Schritte an.

## 5. Upload-Schlüssel sichern

Das private Paket `NOTTLE-AI-Upload-Key-PRIVATE.zip` getrennt und sicher aufbewahren. Es darf nicht öffentlich geteilt oder in GitHub hochgeladen werden. Für spätere Updates werden derselbe Schlüssel und ein höherer `versionCode` benötigt.
