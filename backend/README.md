# Backend

FastAPI service: WebRTC signaling, call sessions, the streaming voice pipeline and the LangGraph agent.
See the [root README](../README.md) for the full architecture.

```bash
uv sync                                         # install (Python 3.12)
uv run uvicorn voice_agent.main:app --reload    # http://127.0.0.1:8000/health
uv run pytest                                   # tests
uv run ruff check . && uv run mypy              # lint + typecheck
```
