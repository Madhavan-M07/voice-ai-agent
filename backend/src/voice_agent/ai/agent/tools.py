"""Receptionist tools exposed to the LLM (clinic facts live in the system prompt, not a tool).

All clinic-specific rules (hours, doctors and their days, phone length) come from the injected
ClinicProfile. Domain problems (bad date, slot taken, wrong phone) are returned as plain-text
results starting with "Error:" so the model can explain and recover. Unexpected exceptions are
caught by ToolNode.
"""

import re
from collections.abc import Callable
from datetime import date, datetime

from langchain_core.tools import BaseTool, tool

from voice_agent.ai.agent.clinic import (
    ClinicProfile,
    Doctor,
    SlotError,
    describe_days,
    parse_date,
    parse_time,
    spoken_time,
    validate_date,
    validate_slot,
)
from voice_agent.storage.appointments import AppointmentRepository, SlotTakenError

Clock = Callable[[], datetime]


def normalize_phone(raw: str, digits: int) -> str | None:
    """Keep the last `digits` digits, dropping spaces, dashes and country codes."""
    only_digits = re.sub(r"\D", "", raw)
    return only_digits[-digits:] if len(only_digits) >= digits else None


def normalize_booking_id(raw: str) -> str:
    """'sfc 2324', 'S F C 2324' or SFC + a unicode dash + 2324 (from the LLM/STT) -> 'SFC-2324'."""
    letters = re.sub(r"[^A-Za-z]", "", raw).upper()
    digits = re.sub(r"\D", "", raw)
    return f"{letters}-{digits}"


def _spoken_day(day: date) -> str:
    return day.strftime("%A %d %B %Y").replace(" 0", " ")


def build_tools(
    repo: AppointmentRepository,
    clock: Clock,
    clinic: ClinicProfile,
    *,
    max_slots_listed: int = 8,
) -> list[BaseTool]:
    def free_slots(doctor: Doctor, day: date) -> list[str]:
        now = clock()
        booked = repo.booked_slots(doctor.id, day)
        return [
            s.strftime("%H:%M")
            for s in clinic.slots()
            if s not in booked and not (day == now.date() and s <= now.time())
        ]

    def short_list(slots: list[str]) -> str:
        shown = ", ".join(slots[:max_slots_listed])
        extra = len(slots) - max_slots_listed
        return f"{shown} and {extra} more" if extra > 0 else shown

    @tool(parse_docstring=True)
    def check_availability(date: str, doctor: str | None = None) -> str:
        """List free appointment times for a date. Call this before offering any time.

        Args:
            date: Date in YYYY-MM-DD format.
            doctor: Optional doctor name, e.g. a surname. Omit to check all doctors.
        """
        try:
            day = parse_date(date)
            validate_date(day, clock(), clinic)
        except SlotError as exc:
            return f"Error: {exc}"
        if doctor:
            found = clinic.find_doctor(doctor)
            if found is None:
                names = ", ".join(d.name for d in clinic.doctors)
                return f"Error: no doctor named '{doctor}'. Our doctors are {names}."
            doctors = [found]
        else:
            doctors = list(clinic.doctors)
        lines = [f"Free times on {_spoken_day(day)}:"]
        for d in doctors:
            if not clinic.works_on(d, day):
                days = describe_days(d.days or clinic.hours.days)
                lines.append(f"- {d.name} ({d.specialty}): not working that day; works {days}.")
                continue
            slots = free_slots(d, day)
            status = short_list(slots) if slots else "fully booked"
            lines.append(f"- {d.name} ({d.specialty}): {status}.")
        return "\n".join(lines)

    @tool(parse_docstring=True)
    def book_appointment(patient_name: str, phone: str, date: str, time: str, doctor: str) -> str:
        """Book an appointment. Only call after the caller has confirmed every detail.

        Args:
            patient_name: Caller's full name.
            phone: Caller's phone number.
            date: Date in YYYY-MM-DD format.
            time: Start time in 24-hour HH:MM format, from check_availability.
            doctor: Doctor name, e.g. a surname.
        """
        name = patient_name.strip()
        if not name:
            return "Error: the patient's name is required."
        normalized = normalize_phone(phone, clinic.phone_digits)
        if normalized is None:
            return f"Error: a valid {clinic.phone_digits}-digit phone number is required."
        found = clinic.find_doctor(doctor)
        if found is None:
            return f"Error: no doctor named '{doctor}'."
        try:
            day, slot = parse_date(date), parse_time(time)
            validate_slot(day, slot, clock(), clinic, found)
            appt = repo.create(
                patient_name=name, phone=normalized, doctor_id=found.id, day=day, slot=slot
            )
        except SlotError as exc:
            return f"Error: {exc}"
        except SlotTakenError:
            alternatives = short_list(free_slots(found, day)) or "none that day"
            return f"Error: {spoken_time(slot)} was just taken. Free times: {alternatives}."
        return (
            f"Booked. Booking ID {appt.booking_id}: {name} with {found.name} "
            f"on {_spoken_day(day)} at {spoken_time(slot)}."
        )

    @tool(parse_docstring=True)
    def cancel_appointment(booking_id: str, phone: str) -> str:
        """Cancel an existing appointment. The phone must match the one used to book.

        Args:
            booking_id: Booking ID given when the appointment was booked.
            phone: Phone number used when booking.
        """
        appt = repo.get(normalize_booking_id(booking_id))
        if appt is None:
            return f"Error: no booking found with ID {booking_id}."
        if normalize_phone(phone, clinic.phone_digits) != appt.phone:
            return "Error: that phone number does not match this booking."
        if appt.status == "cancelled":
            return f"Booking {appt.booking_id} was already cancelled."
        repo.cancel(appt.booking_id)
        return (
            f"Cancelled booking {appt.booking_id} on {_spoken_day(appt.day)} "
            f"at {spoken_time(appt.slot)}."
        )

    return [check_availability, book_appointment, cancel_appointment]
