from datetime import date, datetime, time

import pytest

from voice_agent.ai.agent.clinic import (
    CLINIC,
    SlotError,
    parse_date,
    parse_time,
    spoken_time,
    validate_date,
    validate_slot,
)

# Monday 2026-11-23, 10:15 clinic time.
NOW = datetime(2026, 11, 23, 10, 15)


def test_slots_cover_opening_hours_in_30_minute_steps() -> None:
    slots = CLINIC.slots()
    assert slots[0] == time(9, 0)
    assert slots[-1] == time(16, 30)
    assert len(slots) == 16


@pytest.mark.parametrize(
    ("day", "message"),
    [
        (date(2026, 11, 20), "in the past"),
        (date(2026, 11, 28), "closed on Saturdays"),
        (date(2026, 11, 29), "closed on Sundays"),
        (date(2027, 1, 4), "30 days ahead"),
    ],
)
def test_validate_date_rejects_unbookable_days(day: date, message: str) -> None:
    with pytest.raises(SlotError, match=message):
        validate_date(day, NOW)


def test_validate_date_accepts_today_and_future_weekdays() -> None:
    validate_date(date(2026, 11, 23), NOW)
    validate_date(date(2026, 12, 23), NOW)


def test_validate_slot_rejects_off_grid_and_out_of_hours_times() -> None:
    with pytest.raises(SlotError, match="not a bookable time"):
        validate_slot(date(2026, 11, 24), time(9, 15), NOW)
    with pytest.raises(SlotError, match="not a bookable time"):
        validate_slot(date(2026, 11, 24), time(17, 0), NOW)


def test_validate_slot_rejects_earlier_slot_today() -> None:
    with pytest.raises(SlotError, match="already passed"):
        validate_slot(date(2026, 11, 23), time(10, 0), NOW)
    validate_slot(date(2026, 11, 23), time(10, 30), NOW)


def test_parse_helpers_give_caller_friendly_errors() -> None:
    assert parse_date("2026-11-24") == date(2026, 11, 24)
    assert parse_time("14:30") == time(14, 30)
    with pytest.raises(SlotError, match="YYYY-MM-DD"):
        parse_date("tomorrow")
    with pytest.raises(SlotError, match="HH:MM"):
        parse_time("half past two")


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("rao", "dr-rao"),
        ("Dr. James Lee", "dr-lee"),
        ("dr-lee", "dr-lee"),
        ("smith", None),
        ("", None),
    ],
)
def test_find_doctor_matches_loosely(query: str, expected: str | None) -> None:
    doctor = CLINIC.find_doctor(query)
    assert (doctor.id if doctor else None) == expected


def test_info_known_and_unknown_topics() -> None:
    assert "Monday to Friday, 9 AM to 5 PM" in CLINIC.info("hours")
    assert "Dr. Meera Rao" in CLINIC.info("Doctors")
    assert "Topics I know" in CLINIC.info("parking")


def test_spoken_time_reads_naturally() -> None:
    assert spoken_time(time(9, 0)) == "9 AM"
    assert spoken_time(time(14, 30)) == "2:30 PM"
    assert spoken_time(time(12, 0)) == "12 PM"
