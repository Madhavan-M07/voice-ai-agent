"""LangGraph dialogue graph:

    START -> agent --(tool calls?)--> tools -> agent ... -> END

The agent node never raises: if every LLM provider fails it replies with a safe apology.
"""

import logging
from collections.abc import Sequence

from langchain_core.messages import AIMessage, SystemMessage, trim_messages
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from voice_agent.ai.agent.prompts import build_system_prompt
from voice_agent.ai.agent.state import ReceptionistState
from voice_agent.ai.agent.tools import Clock
from voice_agent.ai.llm.providers import ChatRunnable, provider_of
from voice_agent.clinic import ClinicProfile

logger = logging.getLogger(__name__)

NO_PROVIDER = "none"

ReceptionistGraph = CompiledStateGraph[
    ReceptionistState, None, ReceptionistState, ReceptionistState
]


def apology(clinic: ClinicProfile) -> str:
    return (
        "Sorry, I'm having some trouble right now. Please try again in a moment, "
        f"or call the front desk at {clinic.phone}."
    )


def build_graph(
    llm: ChatRunnable,
    tools: Sequence[BaseTool],
    clock: Clock,
    clinic: ClinicProfile,
    *,
    max_history_messages: int = 30,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> ReceptionistGraph:
    async def agent(state: ReceptionistState) -> dict[str, object]:
        history = trim_messages(
            state["messages"],
            strategy="last",
            token_counter=len,  # count messages, not tokens
            max_tokens=max_history_messages,
            start_on="human",  # never start mid tool-call exchange
        )
        prompt = [SystemMessage(build_system_prompt(clock(), clinic)), *history]
        try:
            reply = await llm.ainvoke(prompt)
        except Exception:
            logger.exception("All LLM providers failed; replying with an apology")
            return {"messages": [AIMessage(apology(clinic))], "provider": NO_PROVIDER}
        return {"messages": [reply], "provider": provider_of(reply)}

    graph = StateGraph(ReceptionistState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", tools_condition)
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=checkpointer or InMemorySaver())
