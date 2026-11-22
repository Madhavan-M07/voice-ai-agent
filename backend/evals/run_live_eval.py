"""Run the scripted conversations in scenarios.yaml against the REAL models and report pass/fail.

Unit tests never call an LLM; this is the regression check for prompt/model changes.
Uses a throwaway database, so data/clinic.db is never touched. Costs Groq free-tier tokens.

    uv run python evals/run_live_eval.py             # Groq chain (normal mode)
    uv run python evals/run_live_eval.py --local     # local Ollama only (slow)
    uv run python evals/run_live_eval.py -v          # also show provider switches and turn logs
"""

import argparse
import asyncio
import re
import sys
import tempfile
import uuid
from pathlib import Path
from statistics import median
from typing import Any

import yaml

from voice_agent.ai.agent.service import ReceptionistAgent, TurnResult
from voice_agent.core.config import get_settings
from voice_agent.core.logging_setup import configure_logging

SCENARIOS = Path(__file__).with_name("scenarios.yaml")
GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def check(turn: TurnResult, spec: dict[str, Any]) -> list[str]:
    """Return the reasons this turn failed (empty list = pass)."""
    text = turn.text.lower()
    problems = [
        f"tool {t} not called" for t in spec.get("expect_tools", []) if t not in turn.tools_called
    ]
    problems += [
        f"tool {t} called too early" for t in spec.get("reject_tools", []) if t in turn.tools_called
    ]
    problems += [f"missing '{p}'" for p in spec.get("expect_text", []) if p.lower() not in text]
    problems += [f"should not say '{p}'" for p in spec.get("reject_text", []) if p.lower() in text]
    return problems


async def run(agent: ReceptionistAgent) -> bool:
    scenarios = yaml.safe_load(SCENARIOS.read_text(encoding="utf-8"))["scenarios"]
    booking_id, latencies, failed = "UNKNOWN", [], 0
    for scenario in scenarios:
        print(f"\n=== {scenario['name']} ===")
        session = uuid.uuid4().hex[:8]
        for spec in scenario["turns"]:
            text = spec["say"].format(booking_id=booking_id)
            turn = await agent.reply(session, text)
            latencies.append(turn.latency_ms)
            if booking_id == "UNKNOWN" and (m := re.search(r"[A-Z]{2,5}\W?\d{4}", turn.text)):
                booking_id = m.group(0)
            problems = check(turn, spec)
            failed += bool(problems)
            status = f"{RED}FAIL: {'; '.join(problems)}{RESET}" if problems else f"{GREEN}ok{RESET}"
            print(f"You:   {text}\nAgent: {turn.text}")
            meta = f"[{turn.provider} · {turn.latency_ms:.0f} ms · tools={turn.tools_called}]"
            print(f"{DIM}       {meta}{RESET} {status}")

    total = sum(len(s["turns"]) for s in scenarios)
    timing = f"p50 {median(latencies):.0f} ms · max {max(latencies):.0f} ms"
    print(f"\n{total - failed}/{total} turns passed · {timing}")
    return failed == 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--local", action="store_true", help="local Ollama only")
    parser.add_argument("-v", "--verbose", action="store_true", help="show turn and fallback logs")
    args = parser.parse_args()
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    configure_logging("INFO" if args.verbose else "WARNING")

    with tempfile.TemporaryDirectory() as tmp:
        update: dict[str, Any] = {"clinic_db_path": Path(tmp) / "eval.db"}
        if args.local:
            update["groq_api_key"] = None
        agent = ReceptionistAgent.from_settings(get_settings().model_copy(update=update))
        passed = asyncio.run(run(agent))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
