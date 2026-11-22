"""Application settings, loaded from environment variables and an optional .env file."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    host: str = "127.0.0.1"
    port: int = 8000

    # LLM: Groq (free tier, primary) with local Ollama as fallback.
    groq_api_key: SecretStr | None = None
    # Groq retires models over time; current list: console.groq.com/docs/models
    groq_model: str = "openai/gpt-oss-20b"
    # Tried in order when the primary fails. Groq rate limits are per model, so these absorb 429s.
    groq_fallback_models: list[str] = ["openai/gpt-oss-120b"]
    groq_reasoning_effort: Literal["low", "medium", "high"] = "low"  # low = fastest replies
    groq_timeout_s: float = 10.0
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_timeout_s: float = 90.0  # CPU-only 3B model; first call also loads it into RAM
    llm_temperature: float = 0.2

    # Clinic receptionist agent.
    clinic_timezone: str = "Asia/Kolkata"
    clinic_db_path: Path = Path("data/clinic.db")


@lru_cache
def get_settings() -> Settings:
    return Settings()
