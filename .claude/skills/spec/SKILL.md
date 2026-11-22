---
name: spec
description: Turn a feature idea into a written spec and implementation plan in docs/specs/ before any code is written. Use when starting a new feature or significant change.
argument-hint: <feature description>
---

Write a spec for: **$ARGUMENTS**

1. If the request is ambiguous on scope or behaviour, ask up to 3 sharp clarifying questions first.
2. Use the `architect` subagent to explore the codebase and propose an approach.
3. Create `docs/specs/YYYY-MM-DD-<kebab-slug>.md` from `docs/specs/_template.md`, filled in completely:
   problem, goals / non-goals, user-visible behaviour, design, files to change, step-by-step plan,
   test plan, risks, and open questions.
4. If the design makes a significant architectural decision, note that an ADR is needed.
5. Stop and present a short summary of the plan. **Do not write implementation code** until the user approves.
