"""Tests for spoken day/time formatting used in prompts and tool results."""

from datetime import date, time

import pytest

from voice_agent.clinic import Weekday, describe_days, spoken_day, spoken_time


def test_spoken_time_reads_naturally() -> None:
    assert spoken_time(time(9, 0)) == "9 AM"
    assert spoken_time(time(14, 30)) == "2:30 PM"
    assert spoken_time(time(12, 0)) == "12 PM"


@pytest.mark.parametrize(
    ("days", "text"),
    [
        (["mon", "tue", "wed", "thu", "fri"], "Monday to Friday"),
        (["fri", "mon"], "Monday and Friday"),
        (["mon", "wed", "fri"], "Monday, Wednesday and Friday"),
        (["sun"], "Sunday"),
    ],
)
def test_describe_days(days: list[Weekday], text: str) -> None:
    assert describe_days(days) == text


def test_spoken_day_drops_leading_zero() -> None:
    assert spoken_day(date(2026, 12, 4)) == "Friday 4 December 2026"
