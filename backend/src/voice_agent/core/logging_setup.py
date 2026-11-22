"""Logging setup shared by the API, the CLI and (later) the voice pipeline.

Levels used across the app:
    WARNING  something degraded (LLM fallback, recursion limit) but the caller still got a reply
    INFO     one summary line per conversation turn (session, provider, latency, tools)
    DEBUG    every tool call with its arguments and result (contains caller details: dev only)
"""

import logging

# Third-party loggers that are noisy at INFO/DEBUG and rarely useful when debugging the agent.
_NOISY_LOGGERS = ("httpx", "httpcore", "groq", "openai", "urllib3", "asyncio", "aiosqlite")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,  # replace any handler a library installed first
    )
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
