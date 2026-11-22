# Frontend

Browser client for voice calls — works on desktop and mobile (Chrome Android, Safari iOS 14.3+).
Plain HTML/CSS/JavaScript, no build step. Served by the FastAPI backend.

Planned for Phase 4:

```
frontend/
  index.html     one-screen UI: "Tap to talk" button, live transcript, call status
  app.js         WebRTC client: getUserMedia (echo cancellation on), SDP offer to /offer, remote audio playback
  styles.css     responsive, mobile-first
```

Mobile notes:
- Microphone needs HTTPS (or localhost). For phone testing use `cloudflared tunnel --url http://localhost:8000`.
- iOS only plays audio after a user tap, so the call always starts from a button.
- Keep the screen awake during a call (Wake Lock API).
