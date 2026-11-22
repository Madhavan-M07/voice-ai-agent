"""Chat with the receptionist agent in the terminal.

uv run voice-agent-chat            # Groq models first, local Ollama as last resort
uv run voice-agent-chat --local    # local Ollama only (offline; slow on CPU)
uv run voice-agent-chat -v         # + one log line per turn (provider, latency, tools)
uv run voice-agent-chat -vv        # + every tool call with arguments and result
"""

import argparse
import asyncio
import sys
import uuid

from voice_agent.ai.agent.service import ReceptionistAgent
from voice_agent.clinic import ClinicConfigError
from voice_agent.core.config import get_settings
from voice_agent.core.logging_setup import configure_logging

DIM, RED, RESET = "\033[2m", "\033[31m", "\033[0m"
EXIT_WORDS = {"exit", "quit", "bye", "q"}
LOG_LEVELS = {0: "WARNING", 1: "INFO", 2: "DEBUG"}


async def chat(agent: ReceptionistAgent, mode: str) -> None:
    session_id = uuid.uuid4().hex[:8]
    print(
        f"{DIM}{agent.clinic.name} · session {session_id} · {mode} · type 'quit' to exit{RESET}\n"
    )
    while True:
        try:
            text = (await asyncio.to_thread(input, "You: ")).strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text.lower() in EXIT_WORDS:
            break

        print("Agent: ", end="", flush=True)
        async for chunk in agent.stream_reply(session_id, text):
            print(chunk, end="", flush=True)
        turn = agent.last_turn(session_id)
        if turn is not None:
            tools = f" · tools: {', '.join(turn.tools_called)}" if turn.tool_calls else ""
            print(f"\n{DIM}[{turn.provider} · {turn.latency_ms:.0f} ms{tools}]{RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with the clinic receptionist agent.")
    parser.add_argument("--local", action="store_true", help="use the local Ollama model only")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="-v: turn logs, -vv: tool calls too"
    )
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    configure_logging(LOG_LEVELS[min(args.verbose, 2)])

    settings = get_settings()
    if args.local:
        settings = settings.model_copy(update={"groq_api_key": None})
    try:
        agent = ReceptionistAgent.from_settings(settings)
    except ClinicConfigError as exc:
        print(f"{RED}{exc}{RESET}", file=sys.stderr)
        sys.exit(1)
    mode = "local Ollama only" if settings.groq_api_key is None else "Groq → Ollama fallback"
    asyncio.run(chat(agent, mode))


if __name__ == "__main__":
    main()
