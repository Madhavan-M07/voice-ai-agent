# Spec: Phase 2 — Text-only clinic receptionist agent

- **Status:** Done. See [Results & deviations](#results--deviations) at the end.
- **Date:** 2026-11-22
- **Related:** ADR-0002 (to write: LLM providers & agent framework), README roadmap Phase 2

## Problem
The voice pipeline (Phases 3–5) needs a "brain": an agent that holds a natural multi-turn conversation,
remembers what the caller said, calls tools to act on real data, and degrades gracefully when the LLM or a
tool fails. Debugging that logic through audio is slow and painful, so it is built and tested as **text first**.

## Goals / Non-goals
**Goals**
- A LangGraph agent acting as receptionist for a fictional clinic ("Sunrise Family Clinic").
- Tools: check availability, book, cancel, clinic info (FAQ).
- Per-session conversation memory (multi-turn: name → date → slot → confirm).
- Reliability: retries on transient LLM errors, Groq → Ollama fallback, tool errors fed back to the model,
  and a safe canned reply if every LLM path fails.
- A streaming interface (`stream_reply`) that Phases 3–5 plug into unchanged.
- A CLI to chat with the agent and see which provider answered and how long it took.
- Fully tested offline: no network, API key or Ollama needed for `uv run pytest`.

**Non-goals**
- Audio, WebRTC, HTTP endpoints for the agent (Phases 3–4).
- Persisting conversation memory across process restarts (in-memory checkpointer now; SQLite in Phase 6).
- Real patient data, auth, multiple clinics, rescheduling as a separate tool (cancel + book covers it).

## Behaviour
Example session (`uv run voice-agent-chat`):
```
You: Hi, I'd like to see a doctor tomorrow morning.
Agent: Sure. Dr. Meera Rao has openings tomorrow at 9:00, 9:30 and 10:30. Which works for you?
You: 9:30. My name is Arjun, phone 98765 43210.
Agent: To confirm: Arjun, tomorrow at 9:30 with Dr. Rao. Shall I book it?
You: Yes.
Agent: Done. Your booking ID is SFC-4821. Anything else?
[illustrative: real transcripts are in Results below]
```
Rules the agent follows (system prompt):
- **Voice-ready output:** short sentences, no markdown, lists or emojis; times spoken naturally.
- **Confirms before acting:** repeats name, date, time and doctor, and books only after an explicit "yes".
- **Never invents data:** availability, booking IDs and clinic facts come only from tool results.
- Today's date and the clinic timezone are injected into the prompt so "tomorrow" or "next Monday" resolve correctly.
- Out-of-scope or medical-advice questions: politely declines and offers to book an appointment;
  for emergencies, tells the caller to contact emergency services.

## Design

**Graph (hand-built, not `create_react_agent`, to own retries and fallback explicitly):**
```
START → agent ──tool_calls?──► tools ──► agent
          │  no tool calls
          ▼
         END
agent raises after retries + fallback exhausted → apology node → END
```
- `state.py`: `ReceptionistState(MessagesState)` plus `provider_used: str | None`.
- `agent` node: system prompt (with today's date) + history → LLM with tools bound.
- `tools` node: LangGraph `ToolNode(handle_tool_errors=True)`, so a tool exception becomes a ToolMessage the
  model can recover from (e.g. "that slot was just taken") instead of crashing the turn.
- Memory: `MemorySaver` checkpointer keyed by `thread_id = session_id`. A loop guard via `recursion_limit` (12).

**LLM providers (`ai/llm/providers.py`):**
```python
groq.bind_tools(tools).with_retry(stop_after_attempt=2)
    .with_fallbacks([ollama.bind_tools(tools).with_retry(stop_after_attempt=1)])
```
- LangChain's `with_retry` / `with_fallbacks` instead of hand-rolled loops: less code, well-tested.
- No `GROQ_API_KEY` → Ollama only (works offline). Request timeout is configurable (default 15 s).
- The provider that answered is read from the response metadata and returned for logging and metrics.

**Tools (`ai/agent/tools.py`)** depend on an `AppointmentRepository` Protocol (injected, not global):
| Tool | Args | Returns |
|------|------|---------|
| `check_availability` | `date`, `doctor?` | free 30-min slots per doctor; error for past dates, weekends, >30 days ahead |
| `book_appointment` | `patient_name`, `phone`, `date`, `time`, `doctor` | booking ID; rejects taken or invalid slots |
| `cancel_appointment` | `booking_id`, `phone` | confirmation; the phone must match the booking |
| ~~`clinic_info`~~ | — | **Removed after live testing:** facts moved into the system prompt (see Results) |

**Domain & storage**
- `ai/agent/clinic.py`: static clinic profile (name, hours Mon–Fri 9:00–17:00, 2 doctors, services, fees) and
  slot rules. Pure functions, no I/O.
- `storage/appointments.py`: `AppointmentRepository` Protocol, `InMemoryAppointmentRepository` (tests) and
  `SqliteAppointmentRepository` (stdlib `sqlite3`, file `backend/data/clinic.db`, gitignored).
  A UNIQUE(doctor, date, time) constraint prevents double-booking at the database level.

**Service boundary (`ai/agent/service.py`)** — the only thing later phases import:
```python
class ReceptionistAgent:
    async def stream_reply(self, session_id: str, text: str) -> AsyncIterator[str]: ...  # text chunks
    async def reply(self, session_id: str, text: str) -> AgentReply: ...  # text, provider, latency_ms
```
`stream_reply` uses LangGraph `stream_mode="messages"`, so Phase 5 can send sentences to TTS while the LLM is still generating.

**New settings (`core/config.py`)**: `llm_timeout_s`, `clinic_timezone` (default `Asia/Kolkata`, see open
questions), `clinic_db_path`.

**New dependencies:** `langgraph`, `langchain-core`, `langchain-groq`, `langchain-ollama`, `tzdata`
(Windows lacks a zoneinfo database). No extra RAM: Ollama only loads when the fallback is used.

**ADR needed: yes.** ADR-0002, "Groq primary + Ollama fallback via LangChain runnables; LangGraph for
dialogue state". This is costly to reverse, because every later phase depends on it.

## Files to change
- `backend/pyproject.toml`: add dependencies and a `voice-agent-chat` script entry point
- `backend/src/voice_agent/core/config.py`: new settings
- `backend/src/voice_agent/storage/appointments.py`: new (repository Protocol, in-memory and SQLite versions)
- `backend/src/voice_agent/ai/agent/clinic.py`: new (clinic profile and slot rules)
- `backend/src/voice_agent/ai/agent/tools.py`: new (4 tools, built from a repository)
- `backend/src/voice_agent/ai/agent/prompts.py`: new (system prompt template)
- `backend/src/voice_agent/ai/agent/state.py`, `graph.py`: new
- `backend/src/voice_agent/ai/agent/service.py`: new (`ReceptionistAgent`)
- `backend/src/voice_agent/ai/llm/providers.py`: new (model factory with retry and fallback)
- `backend/src/voice_agent/cli.py`: new (interactive chat)
- `backend/tests/fakes.py`: new (scripted fake chat model that supports `bind_tools`)
- `backend/tests/storage/test_appointments.py`, `tests/ai/test_clinic.py`, `test_tools.py`, `test_providers.py`,
  `test_graph.py`, `test_service.py`: new
- `docs/adr/0002-llm-providers-and-agent-framework.md`, `CLAUDE.md` (chat command), `README.md` (roadmap)

## Plan
Each step is test-first, passes lint, formatting, type checking and tests, and gets its own commit.
1. **Dependencies and settings:** add packages and config fields; existing tests still pass.
2. **Clinic domain:** slot generation and date validation (weekend, past date, too far ahead, timezone).
3. **Appointment repository:** Protocol, in-memory and SQLite versions; double-booking rejected; cancel needs a matching phone.
4. **Tools:** 4 tools over the repository; clear error messages the LLM can act on.
5. **LLM providers:** factory with retry and fallback; Groq-less mode; reports which provider answered.
6. **Graph:** state, prompt, agent/tools loop, memory, apology node, recursion guard.
7. **Service and CLI:** `reply`/`stream_reply`; CLI shows the provider and latency per turn.
8. **Live check and docs:** run the 6 scripted conversations below against Groq **and** Ollama; record
   latency and failures in this spec; write ADR-0002; update `CLAUDE.md` and the README.

## Test plan
- **Unit (offline, fast):** slot rules and date edge cases; repository (book, double-book, cancel with
  wrong/right phone, SQLite persistence across instances); each tool's success and error output.
- **Providers:** primary raises → fallback answers and the provider is reported; both fail → exception
  propagates; no API key → Ollama only.
- **Graph (scripted fake model):** tool call → tool result → final answer; tool exception → model sees
  the error message; memory: turn 2 sees turn 1 for the same session but **not** for another session; LLM total
  failure → apology text; recursion guard stops a tool-call loop.
- **Service:** `stream_reply` yields chunks that join into the full reply.
- **Live (manual, step 8; marked `@pytest.mark.live` and skipped by default):**
  1. Book a slot end to end  2. Ask a FAQ  3. Cancel with the wrong phone, then the right one
  4. Ask for a weekend date  5. Change your mind mid-booking  6. Ask for medical advice (must decline)

## Risks & open questions
**Risks**
- *qwen2.5:3b tool calling is weaker than Groq's.* Mitigation: few, simple tools with clear arguments; the
  fallback is for resilience, not peak quality; step 8 measures it honestly.
- *Groq free-tier rate limits (HTTP 429)* → retry, then Ollama. Model names get deprecated → the model is a setting.
- *The LLM claims a booking without calling the tool.* Mitigation: the prompt rule plus booking IDs that only
  come from the tool; live test 1 checks the database row exists.
- *Patient names and phones go to Groq.* Fictional demo data only; noted in the README.
- *Small-model latency on CPU* (Ollama about 2–4 s per turn). Acceptable for a fallback; measured in step 8.

**Open questions**
1. Clinic timezone: default `Asia/Kolkata`. Is that right for your demo?
2. Clinic name and doctors: fictional "Sunrise Family Clinic" with Dr. Meera Rao and Dr. James Lee. OK, or your own?
3. Should booking require a phone number? (Recommended: yes, because it's how cancellation is verified.)

## Results & deviations
Live evaluation on 2026-11-22: the 6 scripted conversations (11 turns), run on the Ryzen 5 5600H, 8 GB RAM, no GPU.

| Mode | Scenarios correct | p50 latency | max latency | Notes |
|------|-------------------|-------------|-------------|-------|
| Groq chain (20b → 120b) | **6 / 6** | **814 ms** | 1,956 ms | Rate-limit bursts absorbed by gpt-oss-120b; Ollama never needed |
| Ollama `qwen2.5:3b` only | 4 / 6 | 17,127 ms | 99,571 ms | Booked without calling `check_availability` first; scenario 5 never booked |

**Deviations from the design above, all driven by live testing:**
1. **The Groq model changed:** `llama-3.1-8b-instant` was retired (404). Now `openai/gpt-oss-20b` with
   `reasoning_effort=low` and `reasoning_format=hidden`.
2. **A second Groq model was added:** the free tier allows 8,000 tokens/min per model and each turn costs
   about 1,000 tokens. A 429 now switches to `gpt-oss-120b` (about 1 s) instead of retrying, and only
   network, timeout and 5xx errors are retried.
3. **The `clinic_info` tool was removed:** the model invented a fee ("£40") with facts behind a tool. Facts
   are now inlined in a shorter system prompt.
4. **Booking-ID normalization:** the LLM wrote `SFC‑2324` with a non-breaking hyphen; spoken and STT
   variants now resolve.
5. **Every fallback is logged** with its reason; the first run gave no clue why Ollama was used.
6. **Ollama timeout raised to 90 s.** The measurements show it is an offline last resort, not a real-time
   fallback (see ADR-0002).

**Known gaps (carried forward):**
- The confirm-before-booking rule is prompt-enforced only. Groq followed it in the final run; qwen2.5:3b
  partly ignored it. Consider a code-level confirmation step before Phase 3, where speech-recognition errors
  make confirmation matter more.
- Groq's TPM limit caps throughput to about one call at a time on the free tier.
- Clinic details are a Python constant (`clinic.py`). They should move to a config file so a different
  clinic doesn't need code changes.
