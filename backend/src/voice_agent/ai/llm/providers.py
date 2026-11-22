"""LLM provider wiring: a chain of Groq models (free tier) falling back to local Ollama.

    groq gpt-oss-20b ──fails──► groq gpt-oss-120b ──fails──► ollama qwen2.5:3b

Groq rate limits are per model, so a second Groq model absorbs rate-limit (429) bursts in about
a second, while CPU-only Ollama takes 30-50 s and is a last resort for when Groq is unreachable.

Composition (`compose_chat_model`) is separate from construction (`create_chat_models`) so tests can
inject fake models and exercise retry/fallback without network access.
"""

import logging
from collections.abc import Callable, Sequence
from typing import Any

import groq
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable
from langchain_core.runnables.retry import ExponentialJitterParams
from langchain_core.tools import BaseTool
from langchain_core.tracers.schemas import Run
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama

from voice_agent.core.config import Settings

logger = logging.getLogger(__name__)

ChatRunnable = Runnable[LanguageModelInput, AIMessage]

DEFAULT_BACKOFF: ExponentialJitterParams = {"max": 1.0}  # seconds; caps retry wait

# Retry the same model only for blips (network, 5xx). Rate limits (429), retired models (404) and
# bad keys (401) move straight to the next model: waiting or retrying cannot help a live caller.
TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    groq.APIConnectionError,  # includes APITimeoutError
    groq.InternalServerError,
    TimeoutError,
    ConnectionError,
)


def create_chat_models(settings: Settings) -> tuple[list[BaseChatModel], BaseChatModel]:
    """Return (remote models in priority order, local fallback). No API key -> no remote models."""
    local = ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=settings.llm_temperature,
        keep_alive="10m",  # unloads when idle: this laptop has 8 GB RAM
        client_kwargs={"timeout": settings.ollama_timeout_s},
    )
    if settings.groq_api_key is None:
        return [], local
    remote: list[BaseChatModel] = [
        ChatGroq(
            model=model,
            api_key=settings.groq_api_key,
            temperature=settings.llm_temperature,
            timeout=settings.groq_timeout_s,
            max_retries=0,  # retries are handled by with_retry, once, consistently
            reasoning_effort=settings.groq_reasoning_effort,
            reasoning_format="hidden",  # never let reasoning text reach the caller's ears
        )
        for model in (settings.groq_model, *settings.groq_fallback_models)
    ]
    return remote, local


def compose_chat_model(
    remote: Sequence[BaseChatModel],
    local: BaseChatModel,
    tools: Sequence[BaseTool],
    *,
    attempts_per_model: int = 2,
    backoff: ExponentialJitterParams = DEFAULT_BACKOFF,
    retry_on: tuple[type[BaseException], ...] = TRANSIENT_ERRORS,
) -> ChatRunnable:
    """Bind tools; try each remote model in order (retrying blips), then the local model.

    If everything fails, the first model's error is raised.
    """
    chain: list[ChatRunnable] = [
        model.bind_tools(tools)
        .with_retry(
            retry_if_exception_type=retry_on,
            stop_after_attempt=attempts_per_model,
            exponential_jitter_params=backoff,
        )
        .with_listeners(on_error=_log_failure(_name_of(model)))
        for model in remote
    ]
    chain.append(local.bind_tools(tools))
    first, *rest = chain
    return first.with_fallbacks(rest) if rest else first


def _name_of(model: BaseChatModel) -> str:
    return str(getattr(model, "model_name", None) or getattr(model, "model", None) or model)


def _log_failure(model_name: str) -> Callable[[Run], None]:
    """with_fallbacks switches silently; make every switch, and why, visible in the logs."""

    def log(run: Run) -> None:
        lines = (run.error or "unknown error").strip().splitlines()
        logger.warning("LLM %s failed, trying next model: %s", model_name, lines[-1][:300])

    return log


def provider_of(message: BaseMessage) -> str:
    """Human-readable 'provider · model' for logs/metrics, from response metadata."""
    meta: dict[str, Any] = message.response_metadata or {}
    model = meta.get("model_name") or meta.get("model") or "unknown-model"
    provider = meta.get("model_provider") or ("ollama" if "model" in meta else "unknown")
    return f"{provider} · {model}"
