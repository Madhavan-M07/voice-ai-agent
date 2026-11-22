"""Receptionist tools exposed to the LLM (clinic facts live in the system prompt, not a tool).

Domain problems (bad date, slot taken, wrong phone) are returned as plain-text results starting with
"Error:" so the model can explain and recover. Unexpected exceptions are caught by ToolNode.
"""

import re
from collections.abc import Callable
from datetime import date, datetime

from langchain_core.tools import BaseTool, tool

from voice_agent.ai.agent.clinic import (
    CLINIC,
    ClinicProfile,
    Doctor,
    SlotError,
    parse_date,
    parse_time,
    spoken_time,
    validate_date,
    validate_slot,
)
from voice_agent.storage.appointments import AppointmentRepository, SlotTakenError

Clock = Callable[[], datetime]
MAX_SLOTS_LISTED = 8  # keep spoken answers short


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    return digits[-10:] if len(digits) >= 10 else None


def normalize_booking_id(raw: str) -> str:
    """'sfc 2324', 'S F C 2324' or SFC + a unicode dash + 2324 (from the LLM/STT) -> 'SFC-2324'."""
    letters = re.sub(r"[^A-Za-z]", "", raw).upper()
    digits = re.sub(r"\D", "", raw)
    return f"{letters}-{digits}"


def _spoken_day(day: date) -> str:
    return day.strftime("%A %d %B %Y").replace(" 0", " ")


def build_tools(
    repo: AppointmentRepository, clock: Clock, clinic: ClinicProfile = CLINIC
) -> list[BaseTool]:
    def free_slots(doctor: Doctor, day: date) -> list[str]:
        now = clock()
        booked = repo.booked_slots(doctor.id, day)
        return [
            s.strftime("%H:%M")
            for s in clinic.slots()
            if s not in booked and not (day == now.date() and s <= now.time())
        ]

    @tool(parse_docstring=True)
    def check_availability(date: str, doctor: str | None = None) -> str:
        """List free appointment times for a date. Call this before offering any time.

        Args:
            date: Date in YYYY-MM-DD format.
            doctor: Optional doctor name, e.g. "Rao". Omit to check all doctors.
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
            doctors: tuple[Doctor, ...] = (found,)
        else:
            doctors = clinic.doctors
        lines = [f"Free times on {_spoken_day(day)}:"]
        for d in doctors:
            slots = free_slots(d, day)
            if not slots:
                lines.append(f"- {d.name} ({d.specialty}): fully booked.")
                continue
            shown = ", ".join(slots[:MAX_SLOTS_LISTED])
            more = (
                f" and {len(slots) - MAX_SLOTS_LISTED} more"
                if len(slots) > MAX_SLOTS_LISTED
                else ""
            )
            lines.append(f"- {d.name} ({d.specialty}): {shown}{more}.")
        return "\n".join(lines)

    @tool(parse_docstring=True)
    def book_appointment(patient_name: str, phone: str, date: str, time: str, doctor: str) -> str:
        """Book an appointment. Only call after the caller has confirmed every detail.

        Args:
            patient_name: Caller's full name.
            phone: Caller's 10-digit phone number.
            date: Date in YYYY-MM-DD format.
            time: Start time in 24-hour HH:MM format, from check_availability.
            doctor: Doctor name, e.g. "Rao".
        """
        name = patient_name.strip()
        if not name:
            return "Error: the patient's name is required."
        normalized = normalize_phone(phone)
        if normalized is None:
            return "Error: a valid 10-digit phone number is required."
        found = clinic.find_doctor(doctor)
        if found is None:
            return f"Error: no doctor named '{doctor}'."
        try:
            day, slot = parse_date(date), parse_time(time)
            validate_slot(day, slot, clock(), clinic)
            appt = repo.create(
                patient_name=name, phone=normalized, doctor_id=found.id, day=day, slot=slot
            )
        except SlotError as exc:
            return f"Error: {exc}"
        except SlotTakenError:
            alternatives = ", ".join(free_slots(found, day)[:MAX_SLOTS_LISTED]) or "none that day"
            return f"Error: {spoken_time(slot)} was just taken. Free times: {alternatives}."
        return (
            f"Booked. Booking ID {appt.booking_id}: {name} with {found.name} "
            f"on {_spoken_day(day)} at {spoken_time(slot)}."
        )

    @tool(parse_docstring=True)
    def cancel_appointment(booking_id: str, phone: str) -> str:
        """Cancel an existing appointment. The phone must match the one used to book.

        Args:
            booking_id: Booking ID like SFC-1234.
            phone: Phone number used when booking.
        """
        appt = repo.get(normalize_booking_id(booking_id))
        if appt is None:
            return f"Error: no booking found with ID {booking_id}."
        if normalize_phone(phone) != appt.phone:
            return "Error: that phone number does not match this booking."
        if appt.status == "cancelled":
            return f"Booking {appt.booking_id} was already cancelled."
        repo.cancel(appt.booking_id)
        return (
            f"Cancelled booking {appt.booking_id} on {_spoken_day(appt.day)} "
            f"at {spoken_time(appt.slot)}."
        )

    return [check_availability, book_appointment, cancel_appointment]
