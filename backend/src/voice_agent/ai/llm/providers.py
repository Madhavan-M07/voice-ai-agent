"""LLM provider wiring: Groq (primary, free tier) with retry, falling back to local Ollama.

Composition (`compose_chat_model`) is separate from construction (`create_chat_models`) so tests can
inject fake models and exercise retry/fallback without network access.
"""

from collections.abc import Sequence
from typing import Any

from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable
from langchain_core.runnables.retry import ExponentialJitterParams
from langchain_core.tools import BaseTool
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

from voice_agent.core.config import Settings

ChatRunnable = Runnable[LanguageModelInput, AIMessage]

DEFAULT_BACKOFF: ExponentialJitterParams = {"max": 2.0}  # seconds; caps retry wait


def create_chat_models(settings: Settings) -> tuple[BaseChatModel | None, BaseChatModel]:
    """Return (primary, fallback). Primary is None when no Groq API key is configured."""
    fallback = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=settings.llm_temperature,
        keep_alive="5m",  # unload after idle: this laptop has 8 GB RAM
        client_kwargs={"timeout": settings.llm_timeout_s},
    )
    if settings.groq_api_key is None:
        return None, fallback
    primary = ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_s,
        max_retries=0,  # retries are handled by with_retry below, once, consistently
    )
    return primary, fallback


def compose_chat_model(
    primary: BaseChatModel | None,
    fallback: BaseChatModel,
    tools: Sequence[BaseTool],
    *,
    primary_attempts: int = 2,
    backoff: ExponentialJitterParams = DEFAULT_BACKOFF,
) -> ChatRunnable:
    """Bind tools, retry the primary on any error, then fall back. Errors propagate if both fail."""
    local: ChatRunnable = fallback.bind_tools(tools)
    if primary is None:
        return local
    remote = primary.bind_tools(tools).with_retry(
        stop_after_attempt=primary_attempts, exponential_jitter_params=backoff
    )
    return remote.with_fallbacks([local])


def provider_of(message: BaseMessage) -> str:
    """Human-readable 'provider · model' for logs/metrics, from response metadata."""
    meta: dict[str, Any] = message.response_metadata or {}
    model = meta.get("model_name") or meta.get("model") or "unknown-model"
    provider = meta.get("model_provider") or ("ollama" if "model" in meta else "unknown")
    return f"{provider} · {model}"
