"""Tests for the clinic profile model and its YAML loader."""

from datetime import time
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from fakes import make_clinic
from voice_agent.clinic import WEEKDAYS, ClinicConfigError, load_clinic

CLINIC = make_clinic()


def test_slots_cover_opening_hours_in_30_minute_steps() -> None:
    slots = CLINIC.slots()
    assert slots[0] == time(9, 0)
    assert slots[-1] == time(16, 30)
    assert len(slots) == 16


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


def test_doctor_info_mentions_part_time_days() -> None:
    assert "Dr. James Lee, Pediatrician (Monday and Wednesday)" in PART_TIME.info("doctors")


def test_hours_info_states_closed_days_from_config() -> None:
    assert CLINIC.info("hours").endswith("Closed on Saturday and Sunday.")
    everyday = make_clinic(hours={"open": "09:00", "close": "17:00", "days": list(WEEKDAYS)})
    assert "Closed" not in everyday.info("hours")
