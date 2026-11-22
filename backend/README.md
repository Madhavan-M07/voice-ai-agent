# Backend

Python service: the clinic receptionist agent (LangGraph), its LLM provider chain, appointment storage
and the FastAPI app. Voice (Phase 3) and WebRTC (Phase 4) will be added here.
See the [root README](../README.md) for the full architecture.

```bash
uv sync                                         # install (Python 3.12)
uv run uvicorn voice_agent.main:app --reload    # http://127.0.0.1:8000/health
uv run voice-agent-chat -v                      # chat with the agent (+ per-turn logs)
uv run python evals/run_live_eval.py            # real-model regression check
uv run pytest                                   # tests
uv run ruff check . && uv run mypy              # lint + typecheck
```
