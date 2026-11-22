# 0001. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-11-22

## Context
Architectural decisions get lost in chat threads and commit messages. Both humans and Claude need a durable,
reviewable record of *why* the system is shaped the way it is.

## Decision
Record significant decisions as numbered Markdown ADRs in `docs/adr/`, using `0000-template.md`
(or the `/adr` skill). ADRs are immutable once accepted; changes are made by a new ADR that supersedes the old one.

## Consequences
- New contributors and Claude can recover the reasoning behind the design.
- Small overhead per significant decision.
