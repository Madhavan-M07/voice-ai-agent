# CLAUDE.md

Project memory for Claude Code. Loaded into every session — keep it short, specific, and true.
Update it whenever Claude makes the same mistake twice.

## Project
- **What:** Real-time voice AI agent — user speaks in a browser (desktop/mobile), audio streams over WebRTC
  through VAD → STT → LangGraph agent → TTS, and the reply streams back. Portfolio project.
- **Stack:** Python 3.12 · uv · FastAPI · aiortc (WebRTC) · Silero VAD · faster-whisper · LangGraph/LangChain ·
  LLM chain Groq `gpt-oss-20b` → Groq `gpt-oss-120b` → Ollama `qwen2.5:3b` (ADR-0002) · Piper/Kokoro TTS · SQLite.
- **Constraint: $0 budget, 8 GB RAM laptop, no GPU (Ryzen 5 5600H).** Never suggest paid services or models
  >3B params locally. Keep total runtime RAM under ~3.5 GB.
- **Status:** Phase 2 done (text receptionist agent). Roadmap in `README.md`.

## Commands
Use these exact commands. Do not invent alternatives. **Run all backend commands from `backend/`.**
```bash
install:    uv sync
dev:        uv run uvicorn voice_agent.main:app --reload     # http://127.0.0.1:8000/health
chat:       uv run voice-agent-chat [--local] [-v|-vv]     # talk to the agent; -v turn logs, -vv tool calls
live-eval:  uv run python evals/run_live_eval.py [--local]  # real-model regression check (costs Groq tokens)
test:       uv run pytest
test-one:   uv run pytest tests/ai/test_tools.py::test_cancel_requires_matching_phone
lint:       uv run ruff check .
format:     uv run ruff format .
typecheck:  uv run mypy
```

## Architecture
Full detail lives in `docs/architecture.md` — read it before any structural change.
```
backend/src/voice_agent/
  core/         config.py (Settings; the ONLY place env vars are read), logging_setup.py
  clinic/       clinic domain: profile.py (YAML → validated model), scheduling.py (booking rules),
                time_utils.py (spoken dates/times). No AI, HTTP or audio.
  storage/      appointments.py: SQLite repository (+ in-memory for tests)
  ai/llm/       providers.py: Groq chain → Ollama, retry/fallback, every switch logged
  ai/agent/     tools.py, prompts.py, state.py, graph.py (LangGraph), service.py (ReceptionistAgent)
  api/          FastAPI routes (today: /health). Thin; no business logic.
  cli.py        terminal chat
  ai/speech/ pipeline/ rtc/   planned for Phases 3-4 (empty)
backend/config/clinic.yaml   all clinic business data
backend/evals/  live regression check: scenarios.yaml + run_live_eval.py
backend/tests/  mirrors src/ (tests/clinic, tests/ai, tests/storage, tests/api); fakes.py = test doubles
frontend/       planned (Phase 4)
```
- Dependency rule: `api`/`rtc` → `pipeline` → `ai` → `clinic`/`storage` → `core`. Never the reverse.
- Providers swap via config, never via `if provider == ...` scattered through code.
- **No business data in code.** Anything about a specific clinic (names, hours, doctors, fees, phone
  format, booking-ID prefix, emergency number, timezone) belongs in `config/clinic.yaml`, validated by
  `ClinicProfile`. Tuning knobs go in `core/config.py` Settings. Tests build clinics with `make_clinic()`
  in `tests/fakes.py`, never by reading the shipped YAML.
- Audio is async end-to-end: never block the event loop — run CPU-bound model calls in a thread/executor.

## How to work in this repo
1. **Explore → Plan → Implement → Verify.** For anything bigger than a small fix, read the relevant code and
   propose a plan first (or use `/spec`). Don't write code until the plan is agreed.
2. **Small, reviewable diffs.** One concern per change. No drive-by refactors or reformatting unrelated code.
3. **Tests prove behaviour.** Write or update a failing test first for bug fixes. Run the test, lint and
   typecheck commands before saying a task is done, and report real output — never claim a pass you didn't see.
4. **Match existing patterns.** Look for an existing helper/pattern before adding a new one. Don't add a
   dependency without asking.
5. **Decisions get recorded.** Significant architectural choices → new ADR in `docs/adr/` (use `/adr`).
6. **Ask when blocked** on a product decision; otherwise pick the conventional option and state it.

## Code conventions
- Full type hints; `mypy --strict` must pass. Pydantic models at API boundaries.
- Use `logging.getLogger(__name__)`, never `print`. Log latency per pipeline stage in ms.
- Tests must not need network, a microphone, or downloaded models — mock adapters at the boundary.
- Fail loudly at boundaries: validate external input; don't swallow exceptions.
- No secrets in code, logs, or tests. Config comes from environment variables / `backend/.env`.
- Comments explain *why*, not *what*.

## Git
- Solo project: commit and push directly to `main` (owner's decision). Only push when tests, lint and
  typecheck pass. Commits of ≤5 files, grouped logically. No AI co-author trailers.
- Conventional Commits: `feat(scope): summary` / `fix(scope): …` / `refactor: …` / `test: …` / `docs: …`.
- Never force-push, rewrite shared history, or commit `.env`/credentials.

## Gotchas
<!-- Add hard-won lessons here: flaky tests, env quirks, things that look wrong but are intentional. -->
- Repo lives in OneDrive: uv needs `link-mode = "copy"` (set in `backend/pyproject.toml`) or installs fail with os error 396.
- Python 3.12 is pinned on purpose — ML wheels (faster-whisper, onnxruntime) may lack 3.14 builds on Windows.
- Starlette prints an httpx deprecation warning in tests; harmless, don't "fix" by adding unvetted packages.
- OneDrive sometimes locks `.venv` files ("Access is denied", os error 5) during `uv sync`/`uv add`; just rerun.
- Groq free tier: 8,000 tokens/min **per model**, ~1,000 tokens per turn. Keep the system prompt + tool schemas
  lean. Groq retires models without notice; model IDs live in `core/config.py`, never hard-code them elsewhere.
- Ollama on this CPU takes 30–50 s per turn: last-resort fallback only, never assume it's real-time.
- LLMs emit unicode dashes (e.g. `SFC‑1234` with U+2011); normalize IDs from model/STT text before lookups.
- Clinic facts are in the system prompt on purpose (ADR-0002); don't move them back behind a tool.
- Tests never call real LLMs. After changing prompts, tools or models, run `evals/run_live_eval.py`.

## Debugging
- Wrong answer in chat? Rerun with `uv run voice-agent-chat -vv`: every turn logs provider + latency +
  tools, and every tool call logs its args and result. Most bugs are visible there.
- `ReceptionistAgent.reply()` returns a `TurnResult` (text, provider, latency_ms, tool_calls with
  args/results); `last_turn(session_id)` gives the same after streaming. Use these in tests and evals.
- WARNING `LLM ... failed, trying next model` = fallback happened; the reason (429, 404...) is in the line.
- Inspect bookings: `uv run python -c "import sqlite3; print(sqlite3.connect('data/clinic.db').execute('select * from appointments').fetchall())"`

## Pointers
- Architecture: `docs/architecture.md` · Decisions: `docs/adr/` · Feature specs: `docs/specs/`
- Claude setup (agents, skills, hooks): `docs/claude-workflow.md`
