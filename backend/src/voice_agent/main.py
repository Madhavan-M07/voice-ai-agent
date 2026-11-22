"""FastAPI application entry point.

Run: uv run uvicorn voice_agent.main:app --reload
"""

from fastapi import FastAPI

from voice_agent import __version__
from voice_agent.api import health
from voice_agent.core.config import get_settings
from voice_agent.core.logging_setup import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Voice AI Agent", version=__version__)
    app.include_router(health.router)
    return app


app = create_app()
