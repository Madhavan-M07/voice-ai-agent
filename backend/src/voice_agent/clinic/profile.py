"""Clinic profile: the validated model of `config/clinic.yaml`, and its loader.

Nothing clinic-specific lives in code. Name, hours, doctors (with optional working days), fees,
timezone, phone format, booking-ID prefix and emergency number all come from the YAML file chosen by
`CLINIC_CONFIG_PATH`. The file is validated at startup so mistakes fail fast with a clear message.
"""

from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from voice_agent.clinic.time_utils import WEEKDAYS, Weekday, describe_days, spoken_time, weekday_of


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
    timezone: str = Field(description="IANA timezone name")
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
        return weekday_of(day) in self.hours.days

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

    def working_days(self, doctor: Doctor) -> list[Weekday]:
        return doctor.days or self.hours.days

    def works_on(self, doctor: Doctor, day: date) -> bool:
        return weekday_of(day) in self.working_days(doctor)

    # --- spoken descriptions ------------------------------------------------------------------

    @property
    def open_days(self) -> str:
        return describe_days(self.hours.days)

    @property
    def closed_days(self) -> str | None:
        closed = [d for d in WEEKDAYS if d not in self.hours.days]
        return describe_days(closed) if closed else None

    def info(self, topic: str) -> str:
        """One spoken sentence about a topic. Used to build the system prompt's fact list."""
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
            "Run from the backend/ folder, or set CLINIC_CONFIG_PATH in .env."
        ) from None
    except yaml.YAMLError as exc:
        raise ClinicConfigError(f"Clinic config {path} is not valid YAML: {exc}") from None
    try:
        return ClinicProfile.model_validate(raw)
    except ValidationError as exc:
        raise ClinicConfigError(f"Clinic config {path} is invalid:\n{exc}") from None
