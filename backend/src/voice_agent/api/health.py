from fastapi import APIRouter
from pydantic import BaseModel

from voice_agent import __version__
from voice_agent.core.config import get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str


@router.get("/health")
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__, env=get_settings().app_env)
