"""Clinic profile and appointment slot rules.

Nothing clinic-specific lives in code. The profile (name, hours, doctors, fees, timezone, etc.)
is loaded from a YAML file (`CLINIC_CONFIG_PATH`, default `config/clinic.yaml`) and validated at
startup, so a different clinic needs a different file, not a code change. The rest is pure logic.
"""

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS: tuple[Weekday, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


class SlotError(ValueError):
    """A requested date/time cannot be booked. The message is safe to show the caller."""


class ClinicConfigError(RuntimeError):
    """The clinic config file is missing or invalid."""


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")  # typos in the YAML fail loudly


class Doctor(_Model):
    id: str = Field(pattern=r"^[a-z0-9-]+$", description="Stable id, e.g. dr-rao")
    name: str = Field(min_length=1)
    specialty: str = Field(min_length=1)
    days: list[Weekday] | None = Field(
        default=None, description="Working days; omit to work every day the clinic is open"
    )


class OpeningHours(_Model):
    open: time
    close: time
    days: list[Weekday] = Field(min_length=1)

    @model_validator(mode="after")
    def _close_after_open(self) -> Self:
        if self.close <= self.open:
            raise ValueError("hours.close must be later than hours.open")
        return self


class ClinicProfile(_Model):
    name: str = Field(min_length=1)
    assistant_name: str = Field(
        min_length=1, description="Name the voice agent introduces itself by"
    )
    address: str
    phone: str
    timezone: str = Field(description="IANA timezone, e.g. Asia/Kolkata")
    emergency_number: str
    booking_id_prefix: str = Field(pattern=r"^[A-Z]{2,5}$")
    phone_digits: int = Field(ge=7, le=15, description="Digits in a local phone number")
    hours: OpeningHours
    slot_minutes: int = Field(ge=5, le=240)
    booking_window_days: int = Field(ge=1, le=365)
    doctors: list[Doctor] = Field(min_length=1)
    services: list[str] = Field(default_factory=list)
    fees: str
    insurance: str

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError(f"unknown timezone {value!r}") from None
        return value

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if not self.slots():
            raise ValueError("slot_minutes is longer than the opening hours")
        ids = [d.id for d in self.doctors]
        if len(ids) != len(set(ids)):
            raise ValueError(f"doctor ids must be unique: {ids}")
        for doctor in self.doctors:
            extra = set(doctor.days or []) - set(self.hours.days)
            if extra:
                raise ValueError(
                    f"{doctor.id} works on {sorted(extra)} but the clinic is closed then"
                )
        return self

    # --- time ---------------------------------------------------------------------------------

    def now(self) -> datetime:
        """Current wall-clock time at the clinic (naive, local)."""
        return datetime.now(ZoneInfo(self.timezone)).replace(tzinfo=None)

    def slots(self) -> list[time]:
        """Every bookable start time in a day."""
        result: list[time] = []
        current = datetime.combine(date.min, self.hours.open)
        end = datetime.combine(date.min, self.hours.close)
        while current + timedelta(minutes=self.slot_minutes) <= end:
            result.append(current.time())
            current += timedelta(minutes=self.slot_minutes)
        return result

    def is_open_on(self, day: date) -> bool:
        return WEEKDAYS[day.weekday()] in self.hours.days

    # --- doctors ------------------------------------------------------------------------------

    def find_doctor(self, query: str) -> Doctor | None:
        """Match 'rao', 'Dr. Meera Rao' or 'dr-rao' to a doctor, case-insensitively."""
        q = query.lower().replace("dr.", "").replace("dr ", "").strip()
        if not q:
            return None
        for doctor in self.doctors:
            if q == doctor.id or q in doctor.name.lower():
                return doctor
        return None

    def works_on(self, doctor: Doctor, day: date) -> bool:
        return WEEKDAYS[day.weekday()] in (doctor.days or self.hours.days)

    # --- spoken descriptions ------------------------------------------------------------------

    @property
    def open_days(self) -> str:
        return describe_days(self.hours.days)

    @property
    def closed_days(self) -> str | None:
        closed = [d for d in WEEKDAYS if d not in self.hours.days]
        return describe_days(closed) if closed else None

    def info(self, topic: str) -> str:
        hours = (
            f"{self.open_days}, {spoken_time(self.hours.open)} to {spoken_time(self.hours.close)}"
        )
        closed = f" Closed on {self.closed_days}." if self.closed_days else ""
        doctors = "; ".join(
            f"{d.name}, {d.specialty}" + (f" ({describe_days(d.days)})" if d.days else "")
            for d in self.doctors
        )
        topics = {
            "hours": f"We are open {hours}.{closed}",
            "address": f"{self.name} is at {self.address}.",
            "contact": f"You can reach the front desk at {self.phone}.",
            "services": "We offer " + ", ".join(self.services) + "." if self.services else "",
            "doctors": f"Our doctors are {doctors}.",
            "fees": self.fees,
            "insurance": self.insurance,
        }
        return topics.get(
            topic.lower().strip(),
            f"I don't have information on that. Topics I know: {', '.join(topics)}.",
        )


def load_clinic(path: Path) -> ClinicProfile:
    """Load and validate the clinic profile. Errors name the file and the bad field."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ClinicConfigError(
            f"Clinic config not found: {path.resolve()}. "
            "Create it (see config/clinic.yaml) or set CLINIC_CONFIG_PATH."
        ) from None
    except yaml.YAMLError as exc:
        raise ClinicConfigError(f"Clinic config {path} is not valid YAML: {exc}") from None
    try:
        return ClinicProfile.model_validate(raw)
    except ValidationError as exc:
        raise ClinicConfigError(f"Clinic config {path} is invalid:\n{exc}") from None


def describe_days(days: list[Weekday]) -> str:
    """['mon'..'fri'] -> 'Monday to Friday'; ['mon','wed'] -> 'Monday and Wednesday'."""
    idx = sorted(WEEKDAYS.index(d) for d in set(days))
    names = [_DAY_NAMES[i] for i in idx]
    if len(idx) > 2 and idx == list(range(idx[0], idx[-1] + 1)):
        return f"{names[0]} to {names[-1]}"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise SlotError(f"'{value}' is not a valid date. Use YYYY-MM-DD.") from None


def parse_time(value: str) -> time:
    try:
        return time.fromisoformat(value.strip())
    except ValueError:
        raise SlotError(f"'{value}' is not a valid time. Use 24-hour HH:MM, like 14:30.") from None


def validate_date(day: date, now: datetime, clinic: ClinicProfile) -> None:
    today = now.date()
    if day < today:
        raise SlotError(f"{day.isoformat()} is in the past.")
    if not clinic.is_open_on(day):
        raise SlotError(
            f"The clinic is closed on {day.strftime('%A')}s. We are open {clinic.open_days} only."
        )
    if day > today + timedelta(days=clinic.booking_window_days):
        raise SlotError(f"Bookings open only {clinic.booking_window_days} days ahead.")


def validate_slot(
    day: date, slot: time, now: datetime, clinic: ClinicProfile, doctor: Doctor | None = None
) -> None:
    validate_date(day, now, clinic)
    if doctor is not None and not clinic.works_on(doctor, day):
        raise SlotError(
            f"{doctor.name} doesn't work on {day.strftime('%A')}s. "
            f"{doctor.name} works {describe_days(doctor.days or clinic.hours.days)}."
        )
    if slot not in clinic.slots():
        raise SlotError(
            f"{spoken_time(slot)} is not a bookable time. Appointments start every "
            f"{clinic.slot_minutes} minutes from {spoken_time(clinic.hours.open)}."
        )
    if day == now.date() and slot <= now.time():
        raise SlotError(f"{spoken_time(slot)} today has already passed.")


def spoken_time(t: time) -> str:
    """'09:00' -> '9 AM', '14:30' -> '2:30 PM'. Reads naturally when spoken by TTS."""
    hour = t.hour % 12 or 12
    suffix = "AM" if t.hour < 12 else "PM"
    return f"{hour} {suffix}" if t.minute == 0 else f"{hour}:{t.minute:02d} {suffix}"
