---
name: implement
description: Implement an approved spec or plan step by step with tests, verification and review. Use after /spec is approved, or with a clear, scoped task.
argument-hint: <path to spec, or task description>
---

Implement: **$ARGUMENTS**

1. Read the spec/plan (if a path is given) and `CLAUDE.md`. Ensure you're on a feature branch, not `main`.
2. Work through the plan **one step at a time**. For each step:
   - Write or update tests for the behaviour (test-first for bug fixes).
   - Make the smallest code change that passes them, following existing patterns.
   - Run the project's test, lint and typecheck commands from `CLAUDE.md`. Fix failures before moving on.
3. When all steps are done, run the `code-reviewer` subagent on the diff and address every *Must fix* finding.
   If the change touches auth, input handling, secrets or external integrations, also run `security-auditor`.
4. Update docs touched by the change (README, `docs/architecture.md`, the spec's status).
5. Report: what changed (files), test/lint/typecheck results with real output, and anything left open.
   Do not commit unless asked — suggest `/ship`.
