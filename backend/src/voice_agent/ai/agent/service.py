"""ReceptionistAgent: the single entry point the voice pipeline (Phases 3-5) uses."""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError

from voice_agent.ai.agent.clinic import CLINIC, ClinicProfile
from voice_agent.ai.agent.graph import NO_PROVIDER, apology, build_graph
from voice_agent.ai.agent.tools import build_tools
from voice_agent.ai.llm.providers import compose_chat_model, create_chat_models
from voice_agent.core.config import Settings
from voice_agent.storage.appointments import SqliteAppointmentRepository

logger = logging.getLogger(__name__)

# One turn is at most ~5 agent/tool round trips; stops a model stuck in a tool-call loop.
DEFAULT_RECURSION_LIMIT = 12


@dataclass(frozen=True)
class AgentReply:
    text: str
    provider: str
    latency_ms: float
    tools_called: list[str] = field(default_factory=list)


class ReceptionistAgent:
    def __init__(
        self,
        graph: Any,
        *,
        clinic: ClinicProfile = CLINIC,
        recursion_limit: int = DEFAULT_RECURSION_LIMIT,
    ) -> None:
        self._graph = graph
        self._clinic = clinic
        self._recursion_limit = recursion_limit

    @classmethod
    def from_settings(cls, settings: Settings) -> "ReceptionistAgent":
        tz = ZoneInfo(settings.clinic_timezone)

        def clock() -> datetime:  # naive local clinic time
            return datetime.now(tz).replace(tzinfo=None)

        tools = build_tools(SqliteAppointmentRepository(settings.clinic_db_path), clock)
        primary, fallback = create_chat_models(settings)
        return cls(build_graph(compose_chat_model(primary, fallback, tools), tools, clock))

    def _config(self, session_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": session_id}, "recursion_limit": self._recursion_limit}

    async def reply(self, session_id: str, text: str) -> AgentReply:
        start = perf_counter()
        try:
            state = await self._graph.ainvoke(
                {"messages": [HumanMessage(text)]}, self._config(session_id)
            )
        except GraphRecursionError:
            logger.warning("Session %s hit the recursion limit", session_id)
            return AgentReply(apology(self._clinic), NO_PROVIDER, _ms_since(start))
        messages: list[BaseMessage] = state["messages"]
        return AgentReply(
            text=messages[-1].text,
            provider=state.get("provider", NO_PROVIDER),
            latency_ms=_ms_since(start),
            tools_called=_tools_called_this_turn(messages),
        )

    async def stream_reply(self, session_id: str, text: str) -> AsyncIterator[str]:
        """Yield the spoken reply as text chunks as soon as the LLM produces them."""
        try:
            async for chunk, meta in self._graph.astream(
                {"messages": [HumanMessage(text)]},
                self._config(session_id),
                stream_mode="messages",
            ):
                if (
                    meta.get("langgraph_node") == "agent"
                    and isinstance(chunk, AIMessageChunk | AIMessage)
                    and chunk.text
                ):
                    yield chunk.text
        except GraphRecursionError:
            logger.warning("Session %s hit the recursion limit", session_id)
            yield apology(self._clinic)

    async def last_provider(self, session_id: str) -> str:
        snapshot = await self._graph.aget_state(self._config(session_id))
        return str(snapshot.values.get("provider", NO_PROVIDER))


def _tools_called_this_turn(messages: list[BaseMessage]) -> list[str]:
    names: list[str] = []
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, AIMessage):
            names[:0] = [call["name"] for call in message.tool_calls]
    return names


def _ms_since(start: float) -> float:
    return round((perf_counter() - start) * 1000, 1)
