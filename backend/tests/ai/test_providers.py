import pytest
from langchain_core.messages import AIMessage
from langchain_core.runnables.retry import ExponentialJitterParams
from pydantic import SecretStr

from fakes import ScriptedChatModel, say
from voice_agent.ai.llm.providers import compose_chat_model, create_chat_models, provider_of
from voice_agent.core.config import Settings

FAST: ExponentialJitterParams = {"max": 0.001}


def _model(label: str, *script: object) -> ScriptedChatModel:
    return ScriptedChatModel(script=list(script), label=label)


def test_primary_answers_when_healthy() -> None:
    primary, local = _model("groq", say("hi")), _model("ollama")

    reply = compose_chat_model([primary], local, [], backoff=FAST).invoke("hello")

    assert reply.content == "hi"
    assert provider_of(reply) == "groq · test"
    assert local.calls == 0


def test_transient_error_is_retried_on_the_same_model() -> None:
    primary, local = _model("groq", TimeoutError(), say("second try")), _model("ollama")

    reply = compose_chat_model([primary], local, [], backoff=FAST).invoke("hello")

    assert reply.content == "second try"
    assert primary.calls == 2


def test_non_transient_error_moves_to_next_remote_model_without_retry() -> None:
    # e.g. rate limit (429), retired model (404), bad key (401): retrying cannot help.
    primary = _model("groq-20b", ValueError("rate limited"), say("unused"))
    secondary = _model("groq-120b", say("from the second model"))
    local = _model("ollama")

    reply = compose_chat_model([primary, secondary], local, [], backoff=FAST).invoke("hello")

    assert reply.content == "from the second model"
    assert (primary.calls, secondary.calls, local.calls) == (1, 1, 0)


def test_local_model_is_the_last_resort() -> None:
    primary = _model("groq-20b", TimeoutError(), ConnectionError())
    secondary = _model("groq-120b", ValueError("rate limited"))
    local = _model("ollama", say("local answer"))

    reply = compose_chat_model([primary, secondary], local, [], backoff=FAST).invoke("hello")

    assert reply.content == "local answer"
    assert provider_of(reply) == "ollama · test"


def test_every_switch_is_logged_with_reason(caplog: pytest.LogCaptureFixture) -> None:
    primary, local = _model("groq", ValueError("model not found")), _model("ollama", say("ok"))

    compose_chat_model([primary], local, [], backoff=FAST).invoke("hello")

    assert "trying next model" in caplog.text and "model not found" in caplog.text


def test_raises_when_every_model_fails() -> None:
    primary = _model("groq", TimeoutError(), TimeoutError())
    local = _model("ollama", ConnectionError("ollama down"))

    # LangChain re-raises the first model's error once every fallback has also failed.
    with pytest.raises(TimeoutError):
        compose_chat_model([primary], local, [], backoff=FAST).invoke("hello")
    assert (primary.calls, local.calls) == (2, 1)


def test_no_remote_models_means_local_only() -> None:
    local = _model("ollama", say("offline"))
    assert compose_chat_model([], local, []).invoke("hello").content == "offline"


def test_create_chat_models_skips_groq_without_api_key() -> None:
    remote, local = create_chat_models(Settings(_env_file=None, groq_api_key=None))  # type: ignore[call-arg]
    assert remote == []
    assert local.__class__.__name__ == "ChatOllama"


def test_create_chat_models_builds_groq_chain_in_priority_order() -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        groq_api_key=SecretStr("test-key"),
        groq_model="model-a",
        groq_fallback_models=["model-b"],
    )

    remote, _ = create_chat_models(settings)

    assert [m.model_name for m in remote] == ["model-a", "model-b"]  # type: ignore[attr-defined]


def test_provider_of_handles_missing_metadata() -> None:
    assert provider_of(AIMessage(content="x")) == "unknown · unknown-model"
    assert provider_of(AIMessage(content="x", response_metadata={"model": "qwen2.5:3b"})) == (
        "ollama · qwen2.5:3b"
    )
