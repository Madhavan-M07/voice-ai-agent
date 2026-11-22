"""Booking rules: is this date/time/doctor bookable? Pure functions over a ClinicProfile.

Every rejection raises SlotError with a message that is safe to say to the caller.
"""

from datetime import date, datetime, time, timedelta

from voice_agent.clinic.profile import ClinicProfile, Doctor
from voice_agent.clinic.time_utils import describe_days, spoken_time


class SlotError(ValueError):
    """A requested date/time cannot be booked. The message is safe to show the caller."""


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
            f"{doctor.name} works {describe_days(clinic.working_days(doctor))}."
        )
    if slot not in clinic.slots():
        raise SlotError(
            f"{spoken_time(slot)} is not a bookable time. Appointments start every "
            f"{clinic.slot_minutes} minutes from {spoken_time(clinic.hours.open)}."
        )
    if day == now.date() and slot <= now.time():
        raise SlotError(f"{spoken_time(slot)} today has already passed.")
