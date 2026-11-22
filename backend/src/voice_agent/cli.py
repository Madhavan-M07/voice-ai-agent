"""Chat with the receptionist agent in the terminal.

uv run voice-agent-chat            # Groq if GROQ_API_KEY is set, Ollama fallback
uv run voice-agent-chat --local    # force local Ollama only
"""

import argparse
import asyncio
import logging
import sys
import uuid
from time import perf_counter

from voice_agent.ai.agent.service import ReceptionistAgent
from voice_agent.core.config import get_settings
from voice_agent.core.logging import configure_logging

DIM, RESET = "\033[2m", "\033[0m"
EXIT_WORDS = {"exit", "quit", "bye", "q"}


async def chat(local_only: bool) -> None:
    settings = get_settings()
    if local_only:
        settings = settings.model_copy(update={"groq_api_key": None})
    agent = ReceptionistAgent.from_settings(settings)
    session_id = uuid.uuid4().hex[:8]
    mode = "Ollama only" if settings.groq_api_key is None else "Groq → Ollama fallback"
    print(f"{DIM}Session {session_id} · {mode} · type 'quit' to exit{RESET}\n")

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
        start = perf_counter()
        first_chunk_ms: float | None = None
        async for chunk in agent.stream_reply(session_id, text):
            if first_chunk_ms is None:
                first_chunk_ms = (perf_counter() - start) * 1000
            print(chunk, end="", flush=True)
        total_ms = (perf_counter() - start) * 1000
        provider = await agent.last_provider(session_id)
        first = f"first text {first_chunk_ms:.0f} ms · " if first_chunk_ms is not None else ""
        print(f"\n{DIM}[{provider} · {first}total {total_ms:.0f} ms]{RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat with the clinic receptionist agent.")
    parser.add_argument("--local", action="store_true", help="use local Ollama only")
    args = parser.parse_args()
    configure_logging("WARNING")
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    asyncio.run(chat(args.local))


if __name__ == "__main__":
    main()
