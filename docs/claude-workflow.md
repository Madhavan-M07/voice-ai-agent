# Working with Claude Code in this repo

## Layout
```
CLAUDE.md                 # Team memory: stack, commands, architecture, rules  (committed)
CLAUDE.local.md           # Your personal notes for Claude                      (gitignored)
.claude/
  settings.json           # Permissions (allow/ask/deny) + hooks              (committed)
  settings.local.json     # Your personal overrides                          (gitignored)
  agents/                 # Subagents — specialists with their own context window
    architect.md            plan before building (read-only)
    code-reviewer.md        review the diff (read-only)
    test-writer.md          write/strengthen tests
    debugger.md             root-cause failures
    security-auditor.md     security pass (read-only)
  skills/                 # Workflows you invoke as /slash-commands
    spec/  implement/  fix-issue/  adr/  ship/
  hooks/                  # Deterministic guardrails (Node; run on every tool call)
    session-context.js      inject branch/status/recent commits at session start
    guard-shell.js          block destructive shell cmds; ask on risky ones
    protect-files.js        block edits to .env, keys, lockfiles, .git/
    format-on-edit.js       auto-format edited Python files with the project's ruff
docs/
  architecture.md         # System map (Claude reads before structural changes)
  adr/                    # Architecture Decision Records
  specs/                  # One spec per feature, written before code
```

## The loop
| Step | Command | What happens |
|------|---------|--------------|
| 1. Plan | `/spec add webhook retries` | Architect explores, writes `docs/specs/…md`, waits for approval |
| 2. Decide | `/adr use Redis for job queue` | Records costly-to-reverse decisions |
| 3. Build | `/implement docs/specs/2026-…md` | Step-by-step, test-first, verified, then auto-reviewed |
| 4. Fix | `/fix-issue 42` | Failing test → root cause → minimal fix |
| 5. Ship | `/ship` | Verify → conventional commit → push → PR |

Tips:
- Press **Shift+Tab** to toggle Plan Mode for read-only exploration before changes.
- Ask for a subagent by name: *"use the code-reviewer agent on my changes"*.
- `/clear` between unrelated tasks — fresh context beats a long, polluted one.
- `/memory` to edit CLAUDE.md; when Claude repeats a mistake, add a rule there.
- `/init` on an existing codebase can draft CLAUDE.md content for you to merge in.

## Why each piece exists
- **CLAUDE.md** = advice Claude *should* follow. **Hooks + permissions** = rules that are *enforced*.
  Anything that must never happen belongs in a hook or a `deny` rule, not just in prose.
- **Subagents** keep noisy exploration/review out of your main context and give an independent second opinion.
- **Specs and ADRs** make Claude's plans reviewable artifacts instead of chat scrollback.

## Customising for a new project
1. Fill every `TODO` in `CLAUDE.md` (especially **Commands**) and `docs/architecture.md`.
2. Trim `permissions.allow` in `.claude/settings.json` to your stack's real commands.
3. Add MCP servers in a `.mcp.json` file when you need one (e.g. Postgres, Playwright, GitHub).
4. Add project-specific rules to `guard-shell.js` / `protect-files.js` (e.g. block `migrations/` edits).
5. Hooks need Node.js on PATH.
