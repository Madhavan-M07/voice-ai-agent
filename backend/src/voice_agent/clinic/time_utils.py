"""Day/time helpers that turn dates and times into text a caller hears naturally via TTS."""

from datetime import date, time
from typing import Literal

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAYS: tuple[Weekday, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def weekday_of(day: date) -> Weekday:
    return WEEKDAYS[day.weekday()]


def spoken_time(t: time) -> str:
    """'09:00' -> '9 AM', '14:30' -> '2:30 PM'."""
    hour = t.hour % 12 or 12
    suffix = "AM" if t.hour < 12 else "PM"
    return f"{hour} {suffix}" if t.minute == 0 else f"{hour}:{t.minute:02d} {suffix}"


def spoken_day(day: date) -> str:
    """date(2026, 11, 24) -> 'Tuesday 24 November 2026'."""
    return day.strftime("%A %d %B %Y").replace(" 0", " ")


def describe_days(days: list[Weekday]) -> str:
    """['mon'..'fri'] -> 'Monday to Friday'; ['mon', 'wed'] -> 'Monday and Wednesday'."""
    idx = sorted(WEEKDAYS.index(d) for d in set(days))
    names = [_DAY_NAMES[i] for i in idx]
    if len(idx) > 2 and idx == list(range(idx[0], idx[-1] + 1)):
        return f"{names[0]} to {names[-1]}"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
