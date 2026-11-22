# Voice AI Agent

Real-time conversational voice agent: speak from any browser (desktop or phone), and an LLM agent
listens, reasons, calls tools and talks back — with streaming speech-to-text, LangGraph dialogue
management and text-to-speech over WebRTC. Built entirely on a free / local model stack.

> 🚧 Work in progress — see [Roadmap](#roadmap).

## Architecture

```
Browser mic ──WebRTC──► aiortc audio track
   ► Silero VAD (end of speech)
   ► faster-whisper (speech → text)
   ► LangGraph agent (memory · tools · retry · fallback) ──streams tokens──►
   ► sentence chunker ► Piper/Kokoro TTS (sentence by sentence)
   ► aiortc outbound track ──WebRTC──► Browser speaker
```

| Layer | Technology |
|-------|------------|
| API & signaling | FastAPI |
| Real-time audio | WebRTC (aiortc) |
| Speech-to-text | faster-whisper + Silero VAD |
| LLM | Groq free tier `gpt-oss-20b` → `gpt-oss-120b` → local Ollama `qwen2.5:3b` ([ADR-0002](docs/adr/0002-llm-providers-and-agent-framework.md)) |
| Agent | LangGraph / LangChain |
| Text-to-speech | Piper / Kokoro |
| Storage | SQLite (transcripts, latency metrics) |

## Quick start

Requirements: [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com/) (optional, for local fallback).

```bash
cd backend
uv sync                                         # install deps (Python 3.12)
cp .env.example .env                            # then add your GROQ_API_KEY
uv run uvicorn voice_agent.main:app --reload    # http://127.0.0.1:8000/health
uv run voice-agent-chat                         # chat with the receptionist (add --local for Ollama only)
uv run pytest                                   # tests (offline: no API key or Ollama needed)
```

Real transcript from the Phase 2 live evaluation:
```
You:   Hi, I'd like to book an appointment with Dr Rao tomorrow morning.
Agent: Sure, I can help with that. What is your full name?
       [groq · openai/gpt-oss-20b · 1956 ms · tools=['check_availability']]
You:   10 AM works. My name is Arjun Kumar and my phone is 98765 43210.
Agent: Great. I have you for 10:00 AM with Dr. Rao on Monday the 23rd. Is that okay?
       [groq · openai/gpt-oss-20b · 345 ms · tools=[]]
You:   Yes, please book it.
Agent: Your appointment is booked. Booking ID SFC-7506. See you Monday the 23rd at 10:00 AM.
       [groq · openai/gpt-oss-20b · 778 ms · tools=['book_appointment']]
```

### Configure your own clinic
Nothing clinic-specific is in the code. Edit [`backend/config/clinic.yaml`](backend/config/clinic.yaml),
or point `CLINIC_CONFIG_PATH` in `backend/.env` at your own copy. The file sets:
- name, assistant name, address, phone, timezone, emergency number
- opening hours and days, slot length, booking window
- doctors, each with optional working days
- services, fees, insurance
- phone-number length and booking-ID prefix

The file is validated at startup. A typo, an unknown timezone, or a doctor scheduled on a day the clinic is
closed stops the app with a clear error.

The demo clinic, "Sunrise Family Clinic", is fictional. Don't enter real patient data: conversation text is
sent to Groq's API.

## Project structure

```
backend/                 Python · FastAPI
  src/voice_agent/
    api/                 HTTP routes (health, WebRTC signaling, sessions)
    core/                settings, logging
    rtc/                 WebRTC peer connections & call sessions
    pipeline/            streaming orchestrator, sentence chunker, barge-in
    ai/agent/            LangGraph dialogue agent (memory, tools, retries, fallback)
    ai/llm/              Groq + Ollama providers
    ai/speech/           VAD, speech-to-text, text-to-speech
    storage/             SQLite transcripts & metrics
  tests/
frontend/                browser / mobile WebRTC client
docs/                    architecture, ADRs, feature specs
```

## Roadmap
- [x] Phase 1 — Project skeleton, config, health check, tests
- [x] Phase 2 — Text-only LangGraph agent (memory, tools, retries, fallback) — [spec](docs/specs/2026-11-22-phase2-text-agent.md)
- [ ] Phase 3 — Local voice loop (mic → STT → agent → TTS → speaker)
- [ ] Phase 4 — WebRTC browser/mobile calls with session management
- [ ] Phase 5 — Streaming, barge-in, per-stage latency metrics
- [ ] Phase 6 — Transcript logging, evaluation and analytics

## Latency

_To be measured in Phase 5._

| Stage | p50 | p95 |
|-------|-----|-----|
| STT | – | – |
| LLM first token | – | – |
| TTS first audio | – | – |
| End-to-end | – | – |
