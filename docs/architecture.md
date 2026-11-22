# Architecture

> Living document. Keep it accurate; Claude reads it before structural changes.
> Record *why* decisions were made in `docs/adr/`, not here.

## 1. Context
TODO — What the system does, who uses it, and the external systems it talks to.

```
[User/Client] ──► [This system] ──► [External service A]
                        │
                        └──► [Database]
```

## 2. Components
| Component | Path | Responsibility | Depends on |
|-----------|------|----------------|------------|
| API | `backend/src/voice_agent/api/` | HTTP routes, WebRTC signaling | rtc, core |
| Core | `backend/src/voice_agent/core/` | Settings, logging | — |
| RTC | `backend/src/voice_agent/rtc/` | Peer connections, audio tracks, call sessions | pipeline |
| Pipeline | `backend/src/voice_agent/pipeline/` | Streaming VAD → STT → agent → TTS, barge-in | ai |
| Agent | `backend/src/voice_agent/ai/agent/` | LangGraph dialogue: memory, tools, retries, fallback | ai/llm, storage |
| LLM | `backend/src/voice_agent/ai/llm/` | Groq (primary) / Ollama (fallback) providers | core |
| Speech | `backend/src/voice_agent/ai/speech/` | VAD, STT, TTS models | core |
| Storage | `backend/src/voice_agent/storage/` | SQLite transcripts & metrics | core |
| Frontend | `frontend/` | Browser/mobile WebRTC client | API (HTTP + WebRTC) |

## 3. Key flows
TODO — Describe the 1–3 most important request/data flows step by step.

## 4. Data model
TODO — Core entities and relationships; where state lives.

## 5. Cross-cutting concerns
- **Config & secrets:** environment variables; see `.env.example`.
- **Errors & logging:** TODO
- **Auth:** TODO
- **Observability:** TODO
- **Performance/latency budgets:** TODO

## 6. Constraints & non-goals
TODO
