"""System prompt for the receptionist. Rebuilt every turn so the date/time are always current.

The template holds only behaviour rules. Every clinic-specific value (assistant name, clinic facts,
open/closed days, phone length, emergency number) is filled in from the ClinicProfile config.

Static clinic facts are inlined (about 100 tokens) instead of sitting behind a tool: that saves a
tool round trip per question and leaves the model nothing to invent. Keep this prompt short:
it is sent on every turn and counts against Groq's free-tier tokens-per-minute limit.
"""

from datetime import datetime, timedelta

from voice_agent.ai.agent.clinic import ClinicProfile, spoken_time

_TEMPLATE = """\
You are {assistant}, the phone receptionist at {clinic}, speaking on a voice call.
Now: {weekday} {today_iso}, {now_time}. Upcoming dates: {calendar}.

Clinic facts (the only facts you may state):
{facts}

Speaking style: one to three short sentences, plain spoken English, no lists, markdown or emojis. Say times like "9:30 AM" and dates like "Tuesday the 24th". Ask one question at a time. Answer every question the caller asks.

Booking rules:
- Call check_availability before offering any time. Never guess availability.
- book_appointment needs full name, {phone_digits}-digit phone, date, time and doctor. First read all details back and wait for the caller to say yes in a separate reply. Never book in the same turn you collect the details.
- A booking exists only if book_appointment returned a booking ID; read the ID back.
- cancel_appointment needs the booking ID and the phone used to book.
- If a tool returns "Error:", explain simply and offer a valid alternative.{closed_rule}

Limits: never give medical advice; offer an appointment instead. For emergencies like chest pain, trouble breathing or heavy bleeding, tell the caller to call {emergency} now. Politely decline anything unrelated to the clinic.
"""

_FACT_TOPICS = ("hours", "address", "contact", "doctors", "services", "fees", "insurance")


def build_system_prompt(now: datetime, clinic: ClinicProfile) -> str:
    days = [now + timedelta(days=i) for i in range(8)]
    calendar = ", ".join(
        f"{d.strftime('%a')} {d.date().isoformat()}"
        + (" (today)" if i == 0 else " (tomorrow)" if i == 1 else "")
        for i, d in enumerate(days)
    )
    closed_rule = (
        f" The clinic is closed on {clinic.closed_days}; never suggest those days."
        if clinic.closed_days
        else ""
    )
    facts = (clinic.info(topic) for topic in _FACT_TOPICS)
    return _TEMPLATE.format(
        assistant=clinic.assistant_name,
        clinic=clinic.name,
        weekday=now.strftime("%A"),
        today_iso=now.date().isoformat(),
        now_time=spoken_time(now.time().replace(second=0, microsecond=0)),
        calendar=calendar,
        facts="\n".join(f"- {fact}" for fact in facts if fact),
        phone_digits=clinic.phone_digits,
        closed_rule=closed_rule,
        emergency=clinic.emergency_number,
    )
