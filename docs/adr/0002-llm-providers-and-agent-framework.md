# 0002. LLM provider chain and agent framework

- **Status:** Accepted
- **Date:** 2026-11-22

## Context
The agent must reply in about 1 second to feel natural on a voice call, cost $0, and run on a laptop with
8 GB RAM and no GPU. It needs reliable tool calling, multi-turn memory, and graceful failure.

Measured in Phase 2 (6 scripted conversations, 11 turns):
- Groq free tier, `openai/gpt-oss-20b`: about 0.4–2 s per turn, with reliable tool calling.
- Groq's free tier allows **8,000 tokens per minute per model**, and each turn costs about 1,000 tokens.
  Fast back-and-forth hits HTTP 429 within a minute.
- Ollama `qwen2.5:3b` on the Ryzen 5 5600H CPU: about 30–50 s per turn, with weaker instruction following.
- Groq retires models; the original choice, `llama-3.1-8b-instant`, returned 404 by November 2026.

## Decision
1. **Provider chain:** `groq/openai/gpt-oss-20b` → `groq/openai/gpt-oss-120b` → `ollama/qwen2.5:3b`, built
   with LangChain `with_retry` + `with_fallbacks`.
   - Only transient errors (network, timeout, 5xx) are retried on the same model. A 429, 404 or 401 moves
     straight to the next model, because rate limits are per model and a second Groq model answers in about 1 s.
   - Every switch is logged with its reason.
   - Groq reasoning models run with `reasoning_effort="low"` and `reasoning_format="hidden"`, so reasoning
     text never reaches TTS.
   - Model IDs live in settings, so a retired model is a config change, not a code change.
2. **Ollama is a last resort, not a real-time fallback.** At 30–50 s per turn on CPU it keeps the system
   working offline and in development, but it can't hold a natural voice conversation.
3. **LangGraph** owns the dialogue: a hand-built agent⇄tools graph with a per-session checkpointer, trimmed
   history, tool errors returned to the model as text, a recursion limit, and an apology reply when every
   model fails. It's hand-built rather than `create_react_agent` so failure handling stays explicit and tested.
4. **Static clinic facts go in the system prompt, not behind a tool.** In testing, the model invented a fee
   ("£40") when the facts sat behind `clinic_info`. Inlining them costs about 100 tokens, saves a tool round
   trip, and leaves nothing to invent.

## Alternatives considered
- **Local-only (Ollama).** Free and private, but 30–50 s replies on this hardware. Rejected as the primary.
- **Retry with wait on 429.** Groq suggests waiting 3–8 s, which is dead air on a call. Rejected in favour
  of switching models.
- **Paid APIs (OpenAI, Anthropic).** Better quality, but they break the $0 constraint.
- **Prebuilt `create_react_agent`.** Less code, but it hides the retry, fallback and apology paths we want to
  own and test.

## Consequences
- Normal turns take about 1 s. Bursts are absorbed by the second Groq model, and the system degrades to
  slow-but-working when offline.
- Depends on Groq's free tier staying available. Mitigated by the config-driven model list and the local
  fallback.
- Fictional patient data (names, phones) is sent to Groq, so this is acceptable for a demo only. Real
  patient data would need a provider with a data-processing agreement, or on-prem inference.
- Follow-ups: count tokens per turn and add Groq's free Whisper and Orpheus models as options when
  designing Phase 3 speech (they save RAM compared with local models).
