from datetime import date, datetime, time
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from fakes import make_clinic
from voice_agent.ai.agent.clinic import (
    WEEKDAYS,
    ClinicConfigError,
    SlotError,
    Weekday,
    describe_days,
    load_clinic,
    parse_date,
    parse_time,
    spoken_time,
    validate_date,
    validate_slot,
)

CLINIC = make_clinic()

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


# --- config file loading & validation -------------------------------------------------------

SHIPPED_CONFIG = Path(__file__).parents[2] / "config" / "clinic.yaml"


def test_shipped_clinic_config_is_valid() -> None:
    clinic = load_clinic(SHIPPED_CONFIG)
    assert clinic.name and clinic.doctors and clinic.slots()


def test_load_clinic_reads_every_field_from_the_file(tmp_path: Path) -> None:
    path = tmp_path / "clinic.yaml"
    path.write_text(
        yaml.safe_dump(
            make_clinic(
                name="Hilltop Dental",
                assistant_name="Sam",
                hours={"open": "08:00", "close": "12:00", "days": ["sat", "sun"]},
                slot_minutes=60,
            ).model_dump(mode="json")
        ),
        encoding="utf-8",
    )

    clinic = load_clinic(path)

    assert (clinic.name, clinic.assistant_name) == ("Hilltop Dental", "Sam")
    assert clinic.slots() == [time(8), time(9), time(10), time(11)]
    assert clinic.open_days == "Saturday and Sunday"
    assert clinic.closed_days == "Monday to Friday"


def test_missing_config_file_explains_how_to_fix(tmp_path: Path) -> None:
    with pytest.raises(ClinicConfigError, match="CLINIC_CONFIG_PATH"):
        load_clinic(tmp_path / "nope.yaml")


def test_malformed_yaml_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "clinic.yaml"
    path.write_text("name: [unclosed", encoding="utf-8")
    with pytest.raises(ClinicConfigError, match="not valid YAML"):
        load_clinic(path)


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"hours": {"open": "17:00", "close": "09:00", "days": ["mon"]}}, "close must be later"),
        ({"timezone": "Mars/Olympus"}, "unknown timezone"),
        (
            {"slot_minutes": 240, "hours": {"open": "09:00", "close": "10:00", "days": ["mon"]}},
            "longer than",
        ),
        ({"doctors": []}, "at least 1"),
        ({"booking_id_prefix": "sfc"}, "booking_id_prefix"),
        ({"unknown_field": 1}, "unknown_field"),
        (
            {
                "doctors": [
                    {"id": "a", "name": "A", "specialty": "X"},
                    {"id": "a", "name": "B", "specialty": "Y"},
                ]
            },
            "unique",
        ),
        (
            {"doctors": [{"id": "a", "name": "A", "specialty": "X", "days": ["sun"]}]},
            "clinic is closed",
        ),
    ],
)
def test_invalid_config_is_rejected(overrides: dict[str, object], error: str) -> None:
    with pytest.raises(ValidationError, match=error):
        make_clinic(**overrides)


# --- per-doctor working days ----------------------------------------------------------------

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


def test_doctor_info_mentions_part_time_days() -> None:
    assert "Dr. James Lee, Pediatrician (Monday and Wednesday)" in PART_TIME.info("doctors")


@pytest.mark.parametrize(
    ("days", "text"),
    [
        (["mon", "tue", "wed", "thu", "fri"], "Monday to Friday"),
        (["fri", "mon"], "Monday and Friday"),
        (["mon", "wed", "fri"], "Monday, Wednesday and Friday"),
        (["sun"], "Sunday"),
    ],
)
def test_describe_days(days: list[Weekday], text: str) -> None:
    assert describe_days(days) == text


def test_hours_info_states_closed_days_from_config() -> None:
    assert CLINIC.info("hours").endswith("Closed on Saturday and Sunday.")
    everyday = make_clinic(hours={"open": "09:00", "close": "17:00", "days": list(WEEKDAYS)})
    assert "Closed" not in everyday.info("hours")
