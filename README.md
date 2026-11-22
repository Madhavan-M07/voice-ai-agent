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
| LLM | Groq free tier (primary) → Ollama local model (fallback) |
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
uv run pytest                                   # tests
```

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
- [ ] Phase 2 — Text-only LangGraph agent (memory, tools, retries, fallback)
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
