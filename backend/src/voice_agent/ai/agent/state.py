from langgraph.graph import MessagesState


class ReceptionistState(MessagesState):
    """Conversation messages plus which LLM produced the latest reply (for logs/metrics)."""

    provider: str
