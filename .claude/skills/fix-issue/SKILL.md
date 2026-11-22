---
name: fix-issue
description: Fix a bug end to end — reproduce with a failing test, find the root cause, fix, verify. Accepts a GitHub issue number or a bug description.
argument-hint: <issue number or bug description>
---

Fix: **$ARGUMENTS**

1. If given an issue number and `gh` is available, read it with `gh issue view $ARGUMENTS`.
2. Create a branch `fix/<short-slug>` if on `main`.
3. Use the `debugger` subagent approach: reproduce → write a **failing test** → confirm root cause with evidence.
4. Apply the minimal fix for the root cause (not the symptom). Confirm the new test passes and the full suite stays green.
5. Report root cause, fix, and test evidence. Suggest `/ship` to commit and open a PR.
