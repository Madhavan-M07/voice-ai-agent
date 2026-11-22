from datetime import datetime
from pathlib import Path

import pytest
import yaml
from pydantic import SecretStr

from fakes import ScriptedChatModel, call_tool, make_clinic, say
from voice_agent.ai.agent.graph import NO_PROVIDER, build_graph
from voice_agent.ai.agent.service import ReceptionistAgent
from voice_agent.ai.agent.tools import build_tools
from voice_agent.clinic import ClinicConfigError
from voice_agent.core.config import Settings
from voice_agent.storage.appointments import InMemoryAppointmentRepository

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 23, 10, 15)
CLINIC = make_clinic()


def _agent(model: ScriptedChatModel, recursion_limit: int = 12) -> ReceptionistAgent:
    tools = build_tools(InMemoryAppointmentRepository(), lambda: NOW, CLINIC)
    graph = build_graph(model, tools, lambda: NOW, CLINIC)
    return ReceptionistAgent(graph, clinic=CLINIC, recursion_limit=recursion_limit)


async def test_reply_reports_text_provider_tools_and_latency() -> None:
    model = ScriptedChatModel(
        script=[
            call_tool("check_availability", {"date": "2026-11-24"}),
            say("Dr. Rao is free at 9 AM."),
        ],
        label="groq",
    )

    reply = await _agent(model).reply("s1", "How much is a visit?")

    assert reply.text == "Dr. Rao is free at 9 AM."
    assert reply.provider == "groq · test"
    assert reply.tools_called == ["check_availability"]
    assert reply.latency_ms > 0


async def test_stream_reply_yields_only_spoken_text() -> None:
    model = ScriptedChatModel(
        script=[call_tool("check_availability", {"date": "2026-11-24"}), say("We open at 9 AM.")]
    )
    agent = _agent(model)

    chunks = [c async for c in agent.stream_reply("s1", "When do you open?")]

    assert "".join(chunks) == "We open at 9 AM."
    turn = agent.last_turn("s1")
    assert turn is not None and turn.provider == "fake · test"


async def test_stream_reply_speaks_apology_when_llms_fail() -> None:
    agent = _agent(ScriptedChatModel(script=[ConnectionError()]))

    text = "".join([c async for c in agent.stream_reply("s1", "hello")])

    assert "having some trouble" in text
    turn = agent.last_turn("s1")
    assert turn is not None and turn.provider == NO_PROVIDER


async def test_tool_call_loop_is_stopped_by_recursion_limit() -> None:
    looping = ScriptedChatModel(
        script=[call_tool("check_availability", {"date": "2026-11-24"}, f"c{i}") for i in range(20)]
    )

    reply = await _agent(looping, recursion_limit=6).reply("s1", "hours?")
    streamed = "".join([c async for c in _agent(looping, 6).stream_reply("s2", "hours?")])

    assert "having some trouble" in reply.text and reply.provider == NO_PROVIDER
    assert "having some trouble" in streamed


def test_from_settings_loads_clinic_from_config_file(tmp_path: Path) -> None:
    config = tmp_path / "clinic.yaml"
    config.write_text(
        yaml.safe_dump(make_clinic(name="Hilltop Clinic").model_dump(mode="json")), encoding="utf-8"
    )
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        groq_api_key=SecretStr("k"),
        clinic_config_path=config,
        clinic_db_path=tmp_path / "c.db",
    )

    agent = ReceptionistAgent.from_settings(settings)

    assert agent.clinic.name == "Hilltop Clinic"
    assert (tmp_path / "c.db").exists()


def test_from_settings_fails_fast_on_missing_clinic_config(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, clinic_config_path=tmp_path / "missing.yaml")  # type: ignore[call-arg]
    with pytest.raises(ClinicConfigError):
        ReceptionistAgent.from_settings(settings)


async def test_turn_records_each_tool_call_with_args_and_result() -> None:
    model = ScriptedChatModel(
        script=[call_tool("check_availability", {"date": "2026-11-24"}), say("9 AM is free.")]
    )

    turn = await _agent(model).reply("s1", "Anything tomorrow?")

    [call] = turn.tool_calls
    assert call.name == "check_availability"
    assert call.args == {"date": "2026-11-24"}
    assert call.result.startswith("Free times on Tuesday")


async def test_every_turn_is_logged_for_debugging(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level("DEBUG", logger="voice_agent")
    model = ScriptedChatModel(
        script=[call_tool("check_availability", {"date": "2026-11-24"}), say("9 AM is free.")]
    )

    await _agent(model).reply("abc123", "Anything tomorrow?")

    assert "turn session=abc123 provider=fake · test" in caplog.text
    assert "tools=['check_availability']" in caplog.text
    assert "tool check_availability args={'date': '2026-11-24'} -> Free times" in caplog.text
