import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables.retry import ExponentialJitterParams
from pydantic import SecretStr

from fakes import ScriptedChatModel, say
from voice_agent.ai.llm.providers import compose_chat_model, create_chat_models, provider_of
from voice_agent.core.config import Settings

FAST: ExponentialJitterParams = {"max": 0.001}


def test_primary_answers_when_healthy() -> None:
    primary = ScriptedChatModel(script=[say("hi")], label="groq")
    fallback = ScriptedChatModel(script=[], label="ollama")

    reply = compose_chat_model(primary, fallback, [], backoff=FAST).invoke("hello")

    assert reply.content == "hi"
    assert provider_of(reply) == "groq · test"
    assert fallback.calls == 0


def test_primary_is_retried_before_falling_back() -> None:
    primary = ScriptedChatModel(script=[TimeoutError(), say("second try")], label="groq")
    fallback = ScriptedChatModel(script=[], label="ollama")

    reply = compose_chat_model(primary, fallback, [], backoff=FAST).invoke("hello")

    assert reply.content == "second try"
    assert primary.calls == 2


def test_falls_back_after_primary_exhausts_retries() -> None:
    primary = ScriptedChatModel(script=[TimeoutError(), ConnectionError()], label="groq")
    fallback = ScriptedChatModel(script=[say("local answer")], label="ollama")

    reply = compose_chat_model(primary, fallback, [], backoff=FAST).invoke("hello")

    assert reply.content == "local answer"
    assert provider_of(reply) == "ollama · test"


def test_raises_when_every_provider_fails() -> None:
    primary = ScriptedChatModel(script=[TimeoutError(), TimeoutError()], label="groq")
    fallback = ScriptedChatModel(script=[ConnectionError("ollama down")], label="ollama")

    # LangChain re-raises the primary's error once every fallback has also failed.
    with pytest.raises(TimeoutError):
        compose_chat_model(primary, fallback, [], backoff=FAST).invoke("hello")
    assert (primary.calls, fallback.calls) == (2, 1)


def test_no_primary_means_local_only() -> None:
    fallback = ScriptedChatModel(script=[say("offline")], label="ollama")
    assert compose_chat_model(None, fallback, []).invoke("hello").content == "offline"


def test_create_chat_models_skips_groq_without_api_key() -> None:
    primary, fallback = create_chat_models(Settings(_env_file=None, groq_api_key=None))  # type: ignore[call-arg]
    assert primary is None
    assert fallback.__class__.__name__ == "ChatOllama"


def test_create_chat_models_builds_groq_with_key() -> None:
    settings = Settings(_env_file=None, groq_api_key=SecretStr("test-key"))  # type: ignore[call-arg]
    primary, _ = create_chat_models(settings)
    assert primary is not None and primary.__class__.__name__ == "ChatGroq"


def test_provider_of_handles_missing_metadata() -> None:
    assert provider_of(AIMessage(content="x")) == "unknown · unknown-model"
    assert provider_of(AIMessage(content="x", response_metadata={"model": "qwen2.5:3b"})) == (
        "ollama · qwen2.5:3b"
    )
