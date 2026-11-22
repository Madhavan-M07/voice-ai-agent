"""Clinic profile and appointment slot rules. Pure domain logic: no I/O, no LLM."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta


class SlotError(ValueError):
    """A requested date/time cannot be booked. The message is safe to show the caller."""


@dataclass(frozen=True)
class Doctor:
    id: str
    name: str
    specialty: str


@dataclass(frozen=True)
class ClinicProfile:
    name: str
    address: str
    phone: str
    open_time: time
    close_time: time
    open_weekdays: frozenset[int]  # Monday=0 ... Sunday=6
    slot_minutes: int
    booking_window_days: int
    doctors: tuple[Doctor, ...]
    services: tuple[str, ...]
    fees: str
    insurance: str

    def slots(self) -> list[time]:
        """Every bookable start time in a day."""
        result: list[time] = []
        current = datetime.combine(date.min, self.open_time)
        end = datetime.combine(date.min, self.close_time)
        while current + timedelta(minutes=self.slot_minutes) <= end:
            result.append(current.time())
            current += timedelta(minutes=self.slot_minutes)
        return result

    def find_doctor(self, query: str) -> Doctor | None:
        """Match 'rao', 'Dr. Meera Rao' or 'dr-rao' to a doctor, case-insensitively."""
        q = query.lower().replace("dr.", "").replace("dr ", "").strip()
        if not q:
            return None
        for doctor in self.doctors:
            if q == doctor.id or q in doctor.name.lower():
                return doctor
        return None

    @property
    def open_days(self) -> str:
        if self.open_weekdays == frozenset(range(5)):
            return "Monday to Friday"
        return ", ".join(date(2024, 1, 1 + d).strftime("%A") for d in sorted(self.open_weekdays))

    def info(self, topic: str) -> str:
        hours = f"{self.open_days}, {spoken_time(self.open_time)} to {spoken_time(self.close_time)}"
        doctors = "; ".join(f"{d.name}, {d.specialty}" for d in self.doctors)
        topics = {
            "hours": f"We are open {hours}. Closed on weekends.",
            "address": f"{self.name} is at {self.address}.",
            "contact": f"You can reach the front desk at {self.phone}.",
            "services": "We offer " + ", ".join(self.services) + ".",
            "doctors": f"Our doctors are {doctors}.",
            "fees": self.fees,
            "insurance": self.insurance,
        }
        return topics.get(
            topic.lower().strip(),
            f"I don't have information on that. Topics I know: {', '.join(topics)}.",
        )


CLINIC = ClinicProfile(
    name="Sunrise Family Clinic",
    address="12 Lake View Road, near City Park",
    phone="040 1234 5678",
    open_time=time(9, 0),
    close_time=time(17, 0),
    open_weekdays=frozenset(range(5)),
    slot_minutes=30,
    booking_window_days=30,
    doctors=(
        Doctor(id="dr-rao", name="Dr. Meera Rao", specialty="General Physician"),
        Doctor(id="dr-lee", name="Dr. James Lee", specialty="Pediatrician"),
    ),
    services=(
        "general consultations",
        "child health checkups",
        "vaccinations",
        "basic lab tests",
    ),
    fees="A consultation costs 500 rupees. Follow-up visits within 7 days are free.",
    insurance="We accept most major health insurance cards. Please bring your card to the visit.",
)


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


def validate_date(day: date, now: datetime, clinic: ClinicProfile = CLINIC) -> None:
    today = now.date()
    if day < today:
        raise SlotError(f"{day.isoformat()} is in the past.")
    if day.weekday() not in clinic.open_weekdays:
        raise SlotError(
            f"The clinic is closed on {day.strftime('%A')}s. We are open {clinic.open_days} only."
        )
    if day > today + timedelta(days=clinic.booking_window_days):
        raise SlotError(f"Bookings open only {clinic.booking_window_days} days ahead.")


def validate_slot(day: date, slot: time, now: datetime, clinic: ClinicProfile = CLINIC) -> None:
    validate_date(day, now, clinic)
    if slot not in clinic.slots():
        raise SlotError(
            f"{spoken_time(slot)} is not a bookable time. Appointments start every "
            f"{clinic.slot_minutes} minutes from {spoken_time(clinic.open_time)}."
        )
    if day == now.date() and slot <= now.time():
        raise SlotError(f"{spoken_time(slot)} today has already passed.")


def spoken_time(t: time) -> str:
    """'09:00' -> '9 AM', '14:30' -> '2:30 PM'. Reads naturally when spoken by TTS."""
    hour = t.hour % 12 or 12
    suffix = "AM" if t.hour < 12 else "PM"
    return f"{hour} {suffix}" if t.minute == 0 else f"{hour}:{t.minute:02d} {suffix}"
