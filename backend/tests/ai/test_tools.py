import itertools
import re
from datetime import datetime

import pytest
from langchain_core.tools import BaseTool

from voice_agent.ai.agent.tools import build_tools, normalize_phone
from voice_agent.storage.appointments import InMemoryAppointmentRepository

NOW = datetime(2026, 11, 23, 10, 15)  # Monday


@pytest.fixture
def tools() -> dict[str, BaseTool]:
    counter = itertools.count(1001)
    repo = InMemoryAppointmentRepository(id_factory=lambda: f"SFC-{next(counter)}")
    return {t.name: t for t in build_tools(repo, clock=lambda: NOW)}


def _book(tools: dict[str, BaseTool], **overrides: str) -> str:
    args = {
        "patient_name": "Arjun",
        "phone": "98765 43210",
        "date": "2026-11-24",
        "time": "09:30",
        "doctor": "Rao",
    }
    return str(tools["book_appointment"].invoke(args | overrides))


def test_tools_have_descriptions_and_arg_docs(tools: dict[str, BaseTool]) -> None:
    assert set(tools) == {
        "check_availability",
        "book_appointment",
        "cancel_appointment",
        "clinic_info",
    }
    schema = tools["book_appointment"].args
    assert "HH:MM" in schema["time"]["description"]


def test_check_availability_lists_all_doctors(tools: dict[str, BaseTool]) -> None:
    result = tools["check_availability"].invoke({"date": "2026-11-24"})
    assert "Tuesday 24 November 2026" in result
    assert "Dr. Meera Rao" in result and "Dr. James Lee" in result
    assert "09:00" in result and "and 8 more" in result


def test_check_availability_today_hides_past_slots(tools: dict[str, BaseTool]) -> None:
    result = tools["check_availability"].invoke({"date": "2026-11-23", "doctor": "Lee"})
    assert "Dr. Meera Rao" not in result
    assert "10:00" not in result and "10:30" in result


@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({"date": "2026-11-28"}, "closed on Saturdays"),
        ({"date": "next week"}, "YYYY-MM-DD"),
        ({"date": "2026-11-24", "doctor": "Smith"}, "no doctor named"),
    ],
)
def test_check_availability_errors(
    tools: dict[str, BaseTool], args: dict[str, str], error: str
) -> None:
    result = tools["check_availability"].invoke(args)
    assert result.startswith("Error:") and error in result


def test_book_appointment_success_removes_slot(tools: dict[str, BaseTool]) -> None:
    result = _book(tools)

    assert result.startswith("Booked. Booking ID SFC-1001")
    assert "Dr. Meera Rao" in result and "9:30 AM" in result
    availability = tools["check_availability"].invoke({"date": "2026-11-24", "doctor": "Rao"})
    assert "09:30" not in availability


def test_booking_a_taken_slot_offers_alternatives(tools: dict[str, BaseTool]) -> None:
    _book(tools)
    result = _book(tools, patient_name="Priya", phone="9123456780")
    assert result.startswith("Error: 9:30 AM was just taken")
    assert "09:00" in result


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"patient_name": "  "}, "name is required"),
        ({"phone": "12345"}, "10-digit phone"),
        ({"doctor": "Smith"}, "no doctor named"),
        ({"time": "09:15"}, "not a bookable time"),
        ({"date": "2026-11-29"}, "closed on Sundays"),
    ],
)
def test_book_appointment_validation(
    tools: dict[str, BaseTool], overrides: dict[str, str], error: str
) -> None:
    result = _book(tools, **overrides)
    assert result.startswith("Error:") and error in result


def test_cancel_requires_matching_phone(tools: dict[str, BaseTool]) -> None:
    booking_id = re.search(r"SFC-\d+", _book(tools))
    assert booking_id
    cancel = tools["cancel_appointment"]

    wrong = cancel.invoke({"booking_id": booking_id[0], "phone": "9000000000"})
    right = cancel.invoke({"booking_id": booking_id[0].lower(), "phone": "+91 98765-43210"})
    again = cancel.invoke({"booking_id": booking_id[0], "phone": "9876543210"})

    assert "does not match" in wrong
    assert right.startswith("Cancelled booking SFC-1001")
    assert "already cancelled" in again


def test_cancel_unknown_booking(tools: dict[str, BaseTool]) -> None:
    result = tools["cancel_appointment"].invoke({"booking_id": "SFC-9999", "phone": "9876543210"})
    assert "no booking found" in result


def test_clinic_info(tools: dict[str, BaseTool]) -> None:
    assert "500 rupees" in tools["clinic_info"].invoke({"topic": "fees"})


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("98765 43210", "9876543210"), ("+91-98765-43210", "9876543210"), ("12345", None)],
)
def test_normalize_phone(raw: str, expected: str | None) -> None:
    assert normalize_phone(raw) == expected
