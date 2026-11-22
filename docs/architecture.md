# Architecture

> Living document. Keep it accurate; read it before structural changes.
> *Why* decisions were made lives in `docs/adr/`.

## 1. Context
A voice receptionist for a clinic. A caller talks (desktop or phone browser); the agent checks
availability, books and cancels appointments, and answers questions about the clinic. Built on a $0 stack
that runs on an 8 GB RAM, CPU-only laptop.

```
[Caller: browser / phone] ──(Phase 4: WebRTC audio)──► [FastAPI backend] ──► Groq API (LLM, free tier)
                                                             │          └──► Ollama (local LLM, last resort)
                                                             └──► SQLite (appointments)
          today: terminal chat (cli.py) ─────────────────────┘
```

## 2. Components (`backend/src/voice_agent/`)
| Package | Responsibility | May import |
|---------|----------------|------------|
| `core/` | Settings (`config.py`, the only place env vars are read) and logging setup | — |
| `clinic/` | The clinic domain: validated profile loaded from `config/clinic.yaml`, booking rules, spoken date/time helpers. No AI, HTTP or audio. | `core` |
| `storage/` | Appointment repository (SQLite; in-memory for tests) | — |
| `ai/llm/` | LLM provider chain: Groq models → Ollama, retry/fallback, logging | `core` |
| `ai/agent/` | LangGraph receptionist: tools, prompt, graph, `ReceptionistAgent` service | `clinic`, `storage`, `ai/llm`, `core` |
| `api/` | FastAPI routes (today: `/health`) | `ai`, `core` |
| `cli.py` | Terminal chat for manual testing | `ai/agent`, `clinic`, `core` |
| `ai/speech/` | *Planned (Phase 3):* VAD, speech-to-text, text-to-speech | `core` |
| `pipeline/` | *Planned (Phase 3/5):* streaming audio ⇄ agent orchestration, barge-in | `ai`, `core` |
| `rtc/` | *Planned (Phase 4):* WebRTC connections and call sessions | `pipeline`, `core` |

**Dependency rule:** arrows only point down the table. `clinic/` and `storage/` never import `ai/`;
`ai/` never imports `api/`, `rtc/` or `pipeline/`.

Other top-level folders:
- `backend/config/clinic.yaml`: the clinic profile. **All business data lives here, not in code.**
- `backend/evals/`: live regression check against the real models (`scenarios.yaml` + runner).
- `backend/tests/`: unit tests, mirroring `src/`. They never call an LLM or the network.
- `frontend/`: *Planned (Phase 4):* browser/mobile client.

## 3. Key flow: one caller turn
```
caller text ─► ReceptionistAgent.stream_reply(session_id, text)
                 │
                 ▼  LangGraph thread = session_id (memory via checkpointer)
              [agent node] system prompt (clinic facts + today's date) + trimmed history
                 │   LLM chain: groq gpt-oss-20b ─429/404─► gpt-oss-120b ─fail─► ollama qwen2.5:3b
                 │   every LLM fails → apology reply (never crashes)
                 ├─ tool calls? ─► [tools node] check_availability / book_appointment / cancel_appointment
                 │                   └─ domain errors return "Error: ..." text so the model can recover
                 ▼
              reply text streamed in chunks ─► caller (later: sentence-by-sentence to TTS)
                 │
                 ▼
              TurnResult logged: session, provider, latency, tool calls (+ args/results at DEBUG)
```

## 4. Data model
- **ClinicProfile** (YAML → pydantic): name, assistant name, timezone, hours + open days, slot length,
  booking window, doctors (optional per-doctor working days), services, fees, insurance, phone length,
  booking-ID prefix, emergency number.
- **Appointment** (SQLite table `appointments`): booking_id, patient_name, phone, doctor_id, day, slot,
  status (`booked`/`cancelled`). A partial unique index permits one *active* booking per doctor/slot.
- **Conversation state**: LangGraph in-memory checkpointer, one thread per session (lost on restart;
  persistence is planned for Phase 6).

## 5. Cross-cutting concerns
- **Config:** `core/config.py` (`Settings`, from env / `backend/.env`) for technical settings;
  `config/clinic.yaml` for business data. Both are validated at startup and fail fast with clear errors.
- **Logging:** see `core/logging_setup.py`. WARNING = degraded but handled (fallback, recursion limit);
  INFO = one line per turn; DEBUG = every tool call with arguments (contains caller details: dev only).
- **Errors:** caller-facing problems never raise out of the agent. Bad requests become tool `Error:`
  results, LLM outages become an apology. Config errors stop the app at startup.
- **Latency:** about 0.4–2 s per turn on Groq (measured in Phase 2; see the spec). Ollama on CPU takes
  30–50 s and is offline backup only.
- **Privacy:** caller names and phones go to Groq. The demo uses fictional data only (see ADR-0002).

## 6. Constraints & non-goals
- $0 budget; 8 GB RAM; no GPU. No local model larger than 3B parameters.
- Not a medical system: no advice, no real patient data, no auth (demo).
