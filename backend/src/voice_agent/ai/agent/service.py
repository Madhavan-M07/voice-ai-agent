"""ReceptionistAgent: the single entry point the CLI, API and voice pipeline use.

Every turn is summarised in the logs, so a bad answer can be traced without a debugger:
    INFO   turn session=1a2b provider=groq · gpt-oss-20b latency_ms=812 tools=[book_appointment]
    DEBUG  tool book_appointment args={...} -> Booked. Booking ID SFC-1234 ...
"""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError

from voice_agent.ai.agent.graph import NO_PROVIDER, ReceptionistGraph, apology, build_graph
from voice_agent.ai.agent.state import ReceptionistState
from voice_agent.ai.agent.tools import build_tools
from voice_agent.ai.llm.providers import compose_chat_model, create_chat_models
from voice_agent.clinic import ClinicProfile, load_clinic
from voice_agent.core.config import Settings
from voice_agent.storage.appointments import SqliteAppointmentRepository, booking_id_factory

logger = logging.getLogger(__name__)

_LOG_RESULT_CHARS = 200


@dataclass(frozen=True)
class ToolCall:
    name: str
    args: dict[str, Any]
    result: str


@dataclass(frozen=True)
class TurnResult:
    """What happened in one caller turn. Returned by reply(), and available after stream_reply()."""

    text: str
    provider: str
    latency_ms: float
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def tools_called(self) -> list[str]:
        return [call.name for call in self.tool_calls]


class ReceptionistAgent:
    def __init__(
        self, graph: ReceptionistGraph, *, clinic: ClinicProfile, recursion_limit: int = 12
    ) -> None:
        self._graph = graph
        self.clinic = clinic
        self._recursion_limit = recursion_limit
        self._last_turn: dict[str, TurnResult] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> "ReceptionistAgent":
        """Wire the agent from settings + the clinic config file. Raises ClinicConfigError early."""
        clinic = load_clinic(settings.clinic_config_path)
        repo = SqliteAppointmentRepository(
            settings.clinic_db_path, id_factory=booking_id_factory(clinic.booking_id_prefix)
        )
        tools = build_tools(
            repo, clinic.now, clinic, max_slots_listed=settings.agent_max_slots_listed
        )
        remote, local = create_chat_models(settings)
        graph = build_graph(
            compose_chat_model(remote, local, tools),
            tools,
            clinic.now,
            clinic,
            max_history_messages=settings.agent_max_history_messages,
        )
        logger.info(
            "Agent ready: clinic=%r models=%s db=%s",
            clinic.name,
            [getattr(m, "model_name", "?") for m in remote] + [settings.ollama_model],
            settings.clinic_db_path,
        )
        return cls(graph, clinic=clinic, recursion_limit=settings.agent_recursion_limit)

    async def reply(self, session_id: str, text: str) -> TurnResult:
        """Run one turn and return the full reply."""
        start = perf_counter()
        try:
            await self._graph.ainvoke(self._input(text), self._config(session_id))
        except GraphRecursionError:
            return self._record_recursion_limit(session_id, start)
        return await self._record_turn(session_id, start)

    async def stream_reply(self, session_id: str, text: str) -> AsyncIterator[str]:
        """Yield the spoken reply as text chunks as soon as the LLM produces them."""
        start = perf_counter()
        try:
            async for chunk, meta in self._graph.astream(
                self._input(text), self._config(session_id), stream_mode="messages"
            ):
                from_agent = isinstance(meta, dict) and meta.get("langgraph_node") == "agent"
                if from_agent and isinstance(chunk, AIMessageChunk | AIMessage) and chunk.text:
                    yield chunk.text  # tool results and tool-call stubs are never spoken
        except GraphRecursionError:
            yield self._record_recursion_limit(session_id, start).text
            return
        await self._record_turn(session_id, start)

    def last_turn(self, session_id: str) -> TurnResult | None:
        """Details of the session's most recent turn (provider, latency, tool calls)."""
        return self._last_turn.get(session_id)

    # --- internals ----------------------------------------------------------------------------

    @staticmethod
    def _input(text: str) -> ReceptionistState:
        return {"messages": [HumanMessage(text)]}

    def _config(self, session_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": session_id}, "recursion_limit": self._recursion_limit}

    async def _record_turn(self, session_id: str, start: float) -> TurnResult:
        state = (await self._graph.aget_state(self._config(session_id))).values
        messages: list[BaseMessage] = state["messages"]
        turn = TurnResult(
            text=messages[-1].text,
            provider=str(state.get("provider", NO_PROVIDER)),
            latency_ms=_ms_since(start),
            tool_calls=_tool_calls_this_turn(messages),
        )
        return self._save(session_id, turn)

    def _record_recursion_limit(self, session_id: str, start: float) -> TurnResult:
        logger.warning(
            "turn session=%s hit the recursion limit (%d)", session_id, self._recursion_limit
        )
        turn = TurnResult(apology(self.clinic), NO_PROVIDER, _ms_since(start))
        return self._save(session_id, turn)

    def _save(self, session_id: str, turn: TurnResult) -> TurnResult:
        self._last_turn[session_id] = turn
        logger.info(
            "turn session=%s provider=%s latency_ms=%.0f tools=%s",
            session_id,
            turn.provider,
            turn.latency_ms,
            turn.tools_called,
        )
        for call in turn.tool_calls:
            logger.debug(
                "tool %s args=%s -> %s", call.name, call.args, call.result[:_LOG_RESULT_CHARS]
            )
        return turn


def _tool_calls_this_turn(messages: list[BaseMessage]) -> list[ToolCall]:
    """Pair each tool call since the caller's last message with the tool's result."""
    turn: list[BaseMessage] = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        turn.insert(0, message)
    results = {m.tool_call_id: m.text for m in turn if isinstance(m, ToolMessage)}
    return [
        ToolCall(call["name"], call["args"], results.get(call["id"] or "", ""))
        for m in turn
        if isinstance(m, AIMessage)
        for call in m.tool_calls
    ]


def _ms_since(start: float) -> float:
    return round((perf_counter() - start) * 1000, 1)
