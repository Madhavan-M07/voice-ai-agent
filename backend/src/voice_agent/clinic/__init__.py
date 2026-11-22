"""Clinic domain: the configured clinic profile and its booking rules. No AI, HTTP or audio here."""

from voice_agent.clinic.profile import ClinicConfigError, ClinicProfile, Doctor, load_clinic
from voice_agent.clinic.scheduling import (
    SlotError,
    parse_date,
    parse_time,
    validate_date,
    validate_slot,
)
from voice_agent.clinic.time_utils import (
    WEEKDAYS,
    Weekday,
    describe_days,
    spoken_day,
    spoken_time,
)

__all__ = [
    "WEEKDAYS",
    "ClinicConfigError",
    "ClinicProfile",
    "Doctor",
    "SlotError",
    "Weekday",
    "describe_days",
    "load_clinic",
    "parse_date",
    "parse_time",
    "spoken_day",
    "spoken_time",
    "validate_date",
    "validate_slot",
]
