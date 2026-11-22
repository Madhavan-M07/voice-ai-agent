from datetime import datetime
from typing import Any

import pytest
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool, tool

from fakes import ScriptedChatModel, call_tool, say
from voice_agent.ai.agent.graph import NO_PROVIDER, build_graph
from voice_agent.ai.agent.tools import build_tools
from voice_agent.storage.appointments import InMemoryAppointmentRepository

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 11, 23, 10, 15)  # Monday


def _run(model: ScriptedChatModel, extra_tools: list[BaseTool] | None = None) -> Any:
    tools = build_tools(InMemoryAppointmentRepository(), clock=lambda: NOW) + (extra_tools or [])
    return build_graph(model, tools, clock=lambda: NOW)


def _cfg(session: str) -> RunnableConfig:
    return {"configurable": {"thread_id": session}}


def _user(text: str) -> dict[str, Any]:
    return {"messages": [HumanMessage(text)]}


async def test_calls_tool_then_answers_with_result() -> None:
    model = ScriptedChatModel(
        script=[
            call_tool("check_availability", {"date": "2026-11-24", "doctor": "Rao"}),
            say("Dr. Rao is free at 9 AM."),
        ],
        label="groq",
    )
    graph = _run(model)

    state = await graph.ainvoke(_user("Any slots tomorrow with Dr Rao?"), _cfg("s1"))

    tool_msg = state["messages"][2]
    assert isinstance(tool_msg, ToolMessage) and "Free times on Tuesday" in tool_msg.content
    assert state["messages"][-1].content == "Dr. Rao is free at 9 AM."
    assert state["provider"] == "groq · test"
    # The model's second call saw the tool result.
    assert isinstance(model.seen[1][-1], ToolMessage)


async def test_system_prompt_contains_current_date() -> None:
    model = ScriptedChatModel(script=[say("Hello!")])
    await _run(model).ainvoke(_user("hi"), _cfg("s1"))

    system = model.seen[0][0]
    assert isinstance(system, SystemMessage)
    assert "Monday 2026-11-23" in system.content and "2026-11-24 (tomorrow)" in system.content


async def test_unexpected_tool_exception_is_fed_back_to_model() -> None:
    @tool
    def flaky_lookup() -> str:
        """Always fails."""
        raise RuntimeError("database unavailable")

    model = ScriptedChatModel(
        script=[call_tool("flaky_lookup", {}), say("Sorry, I couldn't check that.")]
    )

    state = await _run(model, [flaky_lookup]).ainvoke(_user("check"), _cfg("s1"))

    tool_msg = state["messages"][2]
    assert isinstance(tool_msg, ToolMessage) and "database unavailable" in tool_msg.content
    assert state["messages"][-1].content == "Sorry, I couldn't check that."


async def test_memory_is_per_session() -> None:
    model = ScriptedChatModel(script=[say("Hi Arjun."), say("You are Arjun."), say("Who?")])
    graph = _run(model)

    await graph.ainvoke(_user("My name is Arjun"), _cfg("caller-a"))
    await graph.ainvoke(_user("What is my name?"), _cfg("caller-a"))
    await graph.ainvoke(_user("What is my name?"), _cfg("caller-b"))

    same_session = [m.content for m in model.seen[1]]
    other_session = [m.content for m in model.seen[2]]
    assert "My name is Arjun" in same_session
    assert "My name is Arjun" not in other_session


async def test_total_llm_failure_returns_apology() -> None:
    model = ScriptedChatModel(script=[ConnectionError("all providers down")])

    state = await _run(model).ainvoke(_user("hello"), _cfg("s1"))

    assert "having some trouble" in state["messages"][-1].content
    assert "040 1234 5678" in state["messages"][-1].content
    assert state["provider"] == NO_PROVIDER
