from datetime import datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from fakes import ScriptedChatModel, call_tool, say
from voice_agent.ai.agent.graph import NO_PROVIDER, build_graph
from voice_agent.ai.agent.service import ReceptionistAgent
from voice_agent.ai.agent.tools import build_tools
from voice_agent.core.config import Settings
from voice_agent.storage.appointments import InMemoryAppointmentRepository

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 23, 10, 15)


def _agent(model: ScriptedChatModel, recursion_limit: int = 12) -> ReceptionistAgent:
    tools = build_tools(InMemoryAppointmentRepository(), clock=lambda: NOW)
    graph = build_graph(model, tools, clock=lambda: NOW)
    return ReceptionistAgent(graph, recursion_limit=recursion_limit)


async def test_reply_reports_text_provider_tools_and_latency() -> None:
    model = ScriptedChatModel(
        script=[call_tool("clinic_info", {"topic": "fees"}), say("It's 500 rupees.")],
        label="groq",
    )

    reply = await _agent(model).reply("s1", "How much is a visit?")

    assert reply.text == "It's 500 rupees."
    assert reply.provider == "groq · test"
    assert reply.tools_called == ["clinic_info"]
    assert reply.latency_ms > 0


async def test_stream_reply_yields_only_spoken_text() -> None:
    model = ScriptedChatModel(
        script=[call_tool("clinic_info", {"topic": "hours"}), say("We open at 9 AM.")]
    )
    agent = _agent(model)

    chunks = [c async for c in agent.stream_reply("s1", "When do you open?")]

    assert "".join(chunks) == "We open at 9 AM."
    assert await agent.last_provider("s1") == "fake · test"


async def test_stream_reply_speaks_apology_when_llms_fail() -> None:
    agent = _agent(ScriptedChatModel(script=[ConnectionError()]))

    text = "".join([c async for c in agent.stream_reply("s1", "hello")])

    assert "having some trouble" in text
    assert await agent.last_provider("s1") == NO_PROVIDER


async def test_tool_call_loop_is_stopped_by_recursion_limit() -> None:
    looping = ScriptedChatModel(
        script=[call_tool("clinic_info", {"topic": "hours"}, f"c{i}") for i in range(20)]
    )

    reply = await _agent(looping, recursion_limit=6).reply("s1", "hours?")
    streamed = "".join([c async for c in _agent(looping, 6).stream_reply("s2", "hours?")])

    assert "having some trouble" in reply.text and reply.provider == NO_PROVIDER
    assert "having some trouble" in streamed


def test_from_settings_wires_sqlite_and_providers(tmp_path: Path) -> None:
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, groq_api_key=SecretStr("k"), clinic_db_path=tmp_path / "c.db"
    )

    ReceptionistAgent.from_settings(settings)

    assert (tmp_path / "c.db").exists()
