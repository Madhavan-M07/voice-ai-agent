"""Graph state for one conversation (one LangGraph thread per caller session)."""

from typing import NotRequired

from langgraph.graph import MessagesState


class ReceptionistState(MessagesState):
    """Conversation messages plus which LLM produced the latest reply (for logs/metrics)."""

    provider: NotRequired[str]  # absent on input; set by the agent node every turn
