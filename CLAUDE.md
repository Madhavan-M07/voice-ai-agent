# CLAUDE.md

Project memory for Claude Code. Loaded into every session — keep it short, specific, and true.
Update it whenever Claude makes the same mistake twice. Fill in every `TODO`.

## Project
- **What:** Real-time voice AI agent — user speaks in a browser (desktop/mobile), audio streams over WebRTC
  through VAD → STT → LangGraph agent → TTS, and the reply streams back. Portfolio project.
- **Stack:** Python 3.12 · uv · FastAPI · aiortc (WebRTC) · Silero VAD · faster-whisper · LangGraph/LangChain ·
  Groq free tier (primary LLM) + Ollama `qwen2.5:3b` (fallback) · Piper/Kokoro TTS · SQLite.
- **Constraint: $0 budget, 8 GB RAM laptop, no GPU (Ryzen 5 5600H).** Never suggest paid services or models
  >3B params locally. Keep total runtime RAM under ~3.5 GB.
- **Status:** Phase 1 done (skeleton). Roadmap in `README.md`.

## Commands
Use these exact commands. Do not invent alternatives. **Run all backend commands from `backend/`.**
```bash
install:    uv sync
dev:        uv run uvicorn voice_agent.main:app --reload     # http://127.0.0.1:8000/health
test:       uv run pytest
test-one:   uv run pytest tests/test_x.py::test_y
lint:       uv run ruff check .
format:     uv run ruff format .
typecheck:  uv run mypy
```

## Architecture
Full detail lives in `docs/architecture.md` — read it before any structural change.
```
backend/src/voice_agent/
  api/          FastAPI routes (health, signaling, sessions, stats). Thin; no business logic.
  core/         config.py (pydantic-settings; the ONLY place env vars are read), logging.py
  rtc/          aiortc peer connections, audio tracks, call session manager
  pipeline/     streaming orchestrator: VAD → STT → agent → TTS, sentence chunker, barge-in
  ai/agent/     LangGraph graph, state, tools, prompts, retries/fallback. No audio or HTTP code.
  ai/llm/       LLM providers (Groq primary, Ollama fallback) behind one Protocol
  ai/speech/    Silero VAD, faster-whisper STT, Piper/Kokoro TTS — each behind a Protocol
  storage/      SQLite transcripts + latency/inference metadata
backend/tests/  mirrors src layout
frontend/       plain HTML/CSS/JS WebRTC client (desktop + mobile), served by FastAPI
```
- Dependency rule: `api`/`rtc` → `pipeline` → `ai` → `storage`/`core`. Never the reverse. `ai/` never imports
  `api`, `rtc` or `pipeline`.
- Providers swap via config, never via `if provider == ...` scattered through code.
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
- No secrets in code, logs, or tests. Config comes from environment variables (see `.env.example`).
- Comments explain *why*, not *what*.

## Git
- Branch from `main`: `feat/…`, `fix/…`, `chore/…`. Never commit directly to `main`.
- Conventional Commits: `feat(scope): summary` / `fix(scope): …` / `refactor: …` / `test: …` / `docs: …`.
- Never force-push, rewrite shared history, or commit `.env`/credentials.

## Gotchas
<!-- Add hard-won lessons here: flaky tests, env quirks, things that look wrong but are intentional. -->
- Repo lives in OneDrive: uv needs `link-mode = "copy"` (set in `backend/pyproject.toml`) or installs fail with os error 396.
- Python 3.12 is pinned on purpose — ML wheels (faster-whisper, onnxruntime) may lack 3.14 builds on Windows.
- Starlette prints an httpx deprecation warning in tests; harmless, don't "fix" by adding unvetted packages.

## Pointers
- Architecture: `docs/architecture.md` · Decisions: `docs/adr/` · Feature specs: `docs/specs/`
- Claude setup (agents, skills, hooks): `docs/claude-workflow.md`
