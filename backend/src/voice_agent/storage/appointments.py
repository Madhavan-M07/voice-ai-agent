"""Appointment persistence: repository Protocol, in-memory (tests) and SQLite implementations."""

import secrets
import sqlite3
import threading
from collections.abc import Callable, Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, replace
from datetime import date, time
from pathlib import Path
from typing import Literal, Protocol

Status = Literal["booked", "cancelled"]


@dataclass(frozen=True)
class Appointment:
    booking_id: str
    patient_name: str
    phone: str
    doctor_id: str
    day: date
    slot: time
    status: Status = "booked"


class SlotTakenError(Exception):
    """The doctor already has an active booking at that date and time."""


class AppointmentRepository(Protocol):
    def booked_slots(self, doctor_id: str, day: date) -> set[time]: ...
    def create(
        self, *, patient_name: str, phone: str, doctor_id: str, day: date, slot: time
    ) -> Appointment: ...
    def get(self, booking_id: str) -> Appointment | None: ...
    def cancel(self, booking_id: str) -> None: ...


def new_booking_id() -> str:
    return f"SFC-{secrets.randbelow(9000) + 1000}"


class InMemoryAppointmentRepository:
    def __init__(self, id_factory: Callable[[], str] = new_booking_id) -> None:
        self._items: dict[str, Appointment] = {}
        self._id_factory = id_factory
        self._lock = threading.Lock()

    def booked_slots(self, doctor_id: str, day: date) -> set[time]:
        return {
            a.slot
            for a in self._items.values()
            if a.doctor_id == doctor_id and a.day == day and a.status == "booked"
        }

    def create(
        self, *, patient_name: str, phone: str, doctor_id: str, day: date, slot: time
    ) -> Appointment:
        with self._lock:
            if slot in self.booked_slots(doctor_id, day):
                raise SlotTakenError
            booking_id = self._id_factory()
            while booking_id in self._items:
                booking_id = self._id_factory()
            appt = Appointment(booking_id, patient_name, phone, doctor_id, day, slot)
            self._items[booking_id] = appt
            return appt

    def get(self, booking_id: str) -> Appointment | None:
        return self._items.get(booking_id.upper())

    def cancel(self, booking_id: str) -> None:
        with self._lock:
            appt = self._items[booking_id.upper()]
            self._items[appt.booking_id] = replace(appt, status="cancelled")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS appointments (
    booking_id   TEXT PRIMARY KEY,
    patient_name TEXT NOT NULL,
    phone        TEXT NOT NULL,
    doctor_id    TEXT NOT NULL,
    day          TEXT NOT NULL,
    slot         TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'booked',
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- Only one ACTIVE booking per doctor/slot; cancelled rows don't block re-booking.
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_slot
    ON appointments (doctor_id, day, slot) WHERE status = 'booked';
"""


class SqliteAppointmentRepository:
    """One short-lived connection per call: safe across the threads LangGraph runs tools in."""

    def __init__(self, path: Path, id_factory: Callable[[], str] = new_booking_id) -> None:
        self._path = path
        self._id_factory = id_factory
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self._path, timeout=5)) as conn, conn:
            conn.row_factory = sqlite3.Row
            yield conn

    def booked_slots(self, doctor_id: str, day: date) -> set[time]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT slot FROM appointments"
                " WHERE doctor_id = ? AND day = ? AND status = 'booked'",
                (doctor_id, day.isoformat()),
            ).fetchall()
        return {time.fromisoformat(r["slot"]) for r in rows}

    def create(
        self, *, patient_name: str, phone: str, doctor_id: str, day: date, slot: time
    ) -> Appointment:
        for _ in range(5):  # retry on (rare) booking-id collision
            appt = Appointment(self._id_factory(), patient_name, phone, doctor_id, day, slot)
            try:
                with self._connect() as conn:
                    conn.execute(
                        "INSERT INTO appointments"
                        " (booking_id, patient_name, phone, doctor_id, day, slot)"
                        " VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            appt.booking_id,
                            patient_name,
                            phone,
                            doctor_id,
                            day.isoformat(),
                            slot.strftime("%H:%M"),
                        ),
                    )
                return appt
            except sqlite3.IntegrityError as exc:
                if "uq_active_slot" in str(exc) or "doctor_id" in str(exc):
                    raise SlotTakenError from exc
        raise RuntimeError("Could not generate a unique booking id")

    def get(self, booking_id: str) -> Appointment | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM appointments WHERE booking_id = ?", (booking_id.upper(),)
            ).fetchone()
        if row is None:
            return None
        return Appointment(
            booking_id=row["booking_id"],
            patient_name=row["patient_name"],
            phone=row["phone"],
            doctor_id=row["doctor_id"],
            day=date.fromisoformat(row["day"]),
            slot=time.fromisoformat(row["slot"]),
            status=row["status"],
        )

    def cancel(self, booking_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE appointments SET status = 'cancelled' WHERE booking_id = ?",
                (booking_id.upper(),),
            )
