"""Tests for booking rules: dates, slots, doctor working days and input parsing."""

from datetime import date, datetime, time

import pytest

from fakes import make_clinic
from voice_agent.clinic import SlotError, parse_date, parse_time, validate_date, validate_slot

CLINIC = make_clinic()

# Monday 2026-11-23, 10:15 clinic time.
NOW = datetime(2026, 11, 23, 10, 15)


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
        validate_date(day, NOW, CLINIC)


def test_validate_date_accepts_today_and_future_weekdays() -> None:
    validate_date(date(2026, 11, 23), NOW, CLINIC)
    validate_date(date(2026, 12, 23), NOW, CLINIC)


def test_validate_slot_rejects_off_grid_and_out_of_hours_times() -> None:
    with pytest.raises(SlotError, match="not a bookable time"):
        validate_slot(date(2026, 11, 24), time(9, 15), NOW, CLINIC)
    with pytest.raises(SlotError, match="not a bookable time"):
        validate_slot(date(2026, 11, 24), time(17, 0), NOW, CLINIC)


def test_validate_slot_rejects_earlier_slot_today() -> None:
    with pytest.raises(SlotError, match="already passed"):
        validate_slot(date(2026, 11, 23), time(10, 0), NOW, CLINIC)
    validate_slot(date(2026, 11, 23), time(10, 30), NOW, CLINIC)


def test_parse_helpers_give_caller_friendly_errors() -> None:
    assert parse_date("2026-11-24") == date(2026, 11, 24)
    assert parse_time("14:30") == time(14, 30)
    with pytest.raises(SlotError, match="YYYY-MM-DD"):
        parse_date("tomorrow")
    with pytest.raises(SlotError, match="HH:MM"):
        parse_time("half past two")


PART_TIME = make_clinic(
    doctors=[
        {"id": "dr-rao", "name": "Dr. Meera Rao", "specialty": "GP"},
        {
            "id": "dr-lee",
            "name": "Dr. James Lee",
            "specialty": "Pediatrician",
            "days": ["mon", "wed"],
        },
    ]
)


def test_doctor_specific_working_days() -> None:
    rao, lee = PART_TIME.doctors
    tuesday = date(2026, 11, 24)
    assert PART_TIME.works_on(rao, tuesday)
    assert not PART_TIME.works_on(lee, tuesday)
    with pytest.raises(
        SlotError, match=r"Dr\. James Lee doesn't work on Tuesdays.*Monday and Wednesday"
    ):
        validate_slot(tuesday, time(10), NOW, PART_TIME, lee)
    validate_slot(date(2026, 11, 25), time(10), NOW, PART_TIME, lee)
