import itertools
from collections.abc import Callable
from datetime import date, time
from pathlib import Path

import pytest

from voice_agent.storage.appointments import (
    AppointmentRepository,
    InMemoryAppointmentRepository,
    SlotTakenError,
    SqliteAppointmentRepository,
)

DAY = date(2026, 11, 24)


def _ids() -> Callable[[], str]:
    counter = itertools.count(1001)
    return lambda: f"SFC-{next(counter)}"


@pytest.fixture(params=["memory", "sqlite"])
def repo(request: pytest.FixtureRequest, tmp_path: Path) -> AppointmentRepository:
    if request.param == "memory":
        return InMemoryAppointmentRepository(id_factory=_ids())
    return SqliteAppointmentRepository(tmp_path / "clinic.db", id_factory=_ids())


def _book(repo: AppointmentRepository, slot: time = time(9, 30), doctor: str = "dr-rao") -> str:
    appt = repo.create(
        patient_name="Arjun", phone="9876543210", doctor_id=doctor, day=DAY, slot=slot
    )
    return appt.booking_id


def test_create_and_get_round_trip(repo: AppointmentRepository) -> None:
    booking_id = _book(repo)

    appt = repo.get(booking_id)

    assert appt is not None
    assert (appt.patient_name, appt.doctor_id, appt.day, appt.slot, appt.status) == (
        "Arjun",
        "dr-rao",
        DAY,
        time(9, 30),
        "booked",
    )
    assert repo.get(booking_id.lower()) == appt  # ids are case-insensitive for callers
    assert repo.booked_slots("dr-rao", DAY) == {time(9, 30)}


def test_double_booking_same_doctor_and_slot_is_rejected(repo: AppointmentRepository) -> None:
    _book(repo)
    with pytest.raises(SlotTakenError):
        _book(repo)


def test_same_slot_with_other_doctor_is_allowed(repo: AppointmentRepository) -> None:
    _book(repo, doctor="dr-rao")
    _book(repo, doctor="dr-lee")
    assert repo.booked_slots("dr-lee", DAY) == {time(9, 30)}


def test_cancel_frees_the_slot_for_rebooking(repo: AppointmentRepository) -> None:
    booking_id = _book(repo)

    repo.cancel(booking_id)

    cancelled = repo.get(booking_id)
    assert cancelled is not None and cancelled.status == "cancelled"
    assert repo.booked_slots("dr-rao", DAY) == set()
    _book(repo)  # does not raise


def test_get_unknown_booking_returns_none(repo: AppointmentRepository) -> None:
    assert repo.get("SFC-0000") is None


def test_sqlite_persists_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "clinic.db"
    booking_id = _book(SqliteAppointmentRepository(path, id_factory=_ids()))

    reopened = SqliteAppointmentRepository(path)

    assert reopened.get(booking_id) is not None
