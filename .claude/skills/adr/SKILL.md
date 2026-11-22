---
name: adr
description: Record an Architecture Decision Record in docs/adr/. Use when choosing a framework, database, protocol, pattern, or any decision that is costly to reverse.
argument-hint: <decision title>
---

Create an ADR for: **$ARGUMENTS**

1. List `docs/adr/` and pick the next number (4 digits, e.g. `0007`).
2. Copy `docs/adr/0000-template.md` to `docs/adr/NNNN-<kebab-title>.md` and fill it in from the conversation
   and codebase: context, decision, alternatives considered (with why rejected), and consequences (good and bad).
3. Status is `Proposed` unless the user says it's accepted. If it supersedes an older ADR, update the old one's
   status to `Superseded by NNNN`.
4. If the decision changes the architecture summary, update `docs/architecture.md` and the Architecture section of `CLAUDE.md`.
