---
name: ship
description: Verify, commit with a Conventional Commit message, push the branch, and open a PR. Only run when the user explicitly invokes /ship.
argument-hint: [optional PR title or notes]
disable-model-invocation: true
---

Ship the current work. $ARGUMENTS

1. `git status` and `git diff` — confirm only intended changes are present; no secrets, debug logging or stray files.
2. Run the full test, lint and typecheck commands from `CLAUDE.md`. **Stop and report if anything fails.**
3. If on `main`, create a branch first (`feat/…` / `fix/…` / `chore/…`).
4. Stage the relevant files explicitly (no blind `git add -A`) and commit with a Conventional Commit message:
   `type(scope): imperative summary` + a body explaining *why*.
5. Push with `git push -u origin <branch>` (never force).
6. If `gh` is available, open a PR with `gh pr create`: summary, what changed, how it was tested, risks,
   and a link to the spec/ADR if any. Return the PR URL.
