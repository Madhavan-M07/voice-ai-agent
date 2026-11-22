"""ReceptionistAgent: the single entry point the voice pipeline (Phases 3-5) uses."""

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphRecursionError

from voice_agent.ai.agent.clinic import ClinicProfile, load_clinic
from voice_agent.ai.agent.graph import NO_PROVIDER, apology, build_graph
from voice_agent.ai.agent.tools import build_tools
from voice_agent.ai.llm.providers import compose_chat_model, create_chat_models
from voice_agent.core.config import Settings
from voice_agent.storage.appointments import SqliteAppointmentRepository, booking_id_factory

logger = logging.getLogger(__name__)


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
        clinic: ClinicProfile,
        recursion_limit: int = 12,
    ) -> None:
        self._graph = graph
        self.clinic = clinic
        self._recursion_limit = recursion_limit

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
        return cls(graph, clinic=clinic, recursion_limit=settings.agent_recursion_limit)

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
            return AgentReply(apology(self.clinic), NO_PROVIDER, _ms_since(start))
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
            yield apology(self.clinic)

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
