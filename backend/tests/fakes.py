"""Test doubles shared across the test suite."""

from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from voice_agent.ai.agent.clinic import ClinicProfile


class ScriptedChatModel(BaseChatModel):
    """Returns (or raises) the scripted items in order. Records every prompt it receives."""

    script: list[Any]  # AIMessage to return, or Exception to raise
    label: str = "fake"
    seen: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    @property
    def calls(self) -> int:
        return len(self.seen)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.seen.append(list(messages))
        if self.calls > len(self.script):
            raise AssertionError(f"{self.label}: script exhausted after {len(self.script)} calls")
        item = self.script[self.calls - 1]
        if isinstance(item, Exception):
            raise item
        message = item.model_copy(
            update={"response_metadata": {"model_provider": self.label, "model_name": "test"}}
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":  # type: ignore[override]
        return self


def say(text: str) -> AIMessage:
    return AIMessage(content=text)


def call_tool(name: str, args: dict[str, Any], call_id: str = "call-1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def make_clinic(**overrides: Any) -> ClinicProfile:
    """A test clinic built in code, so tests never depend on the shipped config/clinic.yaml."""
    data: dict[str, Any] = {
        "name": "Sunrise Family Clinic",
        "assistant_name": "Asha",
        "address": "12 Lake View Road, near City Park",
        "phone": "040 1234 5678",
        "timezone": "Asia/Kolkata",
        "emergency_number": "112",
        "booking_id_prefix": "SFC",
        "phone_digits": 10,
        "hours": {"open": "09:00", "close": "17:00", "days": ["mon", "tue", "wed", "thu", "fri"]},
        "slot_minutes": 30,
        "booking_window_days": 30,
        "doctors": [
            {"id": "dr-rao", "name": "Dr. Meera Rao", "specialty": "General Physician"},
            {"id": "dr-lee", "name": "Dr. James Lee", "specialty": "Pediatrician"},
        ],
        "services": ["general consultations", "vaccinations"],
        "fees": "A consultation costs 500 rupees.",
        "insurance": "We accept most insurance cards.",
    }
    return ClinicProfile.model_validate(data | overrides)
