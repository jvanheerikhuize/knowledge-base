---
name: kb-prospective-memory-that-fires
type: semantic
description: kb.py due (CLI + MCP) plus a daily kb-due.yml workflow surface a prospective entry's due date before it lapses, not just after
confidence: high
source: ROADMAP.md Phase 5, shipped 2026-08-01
created: 2026-08-01
last_verified: 2026-08-01
links: [kb-roadmap, kb-entry-status-model, kb-over-mcp]
---

**The gap.** `prospective/` entries carry a `due:` field, but nothing
surfaced it except `kb.py triage`, and only after the date had already
passed — the one memory type that is about the future was otherwise inert
between sessions.

**What shipped.** `due_report()` in `kb.py`, mirroring how `triage_report`
and `status_report` are each one function three surfaces agree on by
construction:

- `kb.py due [--within Nd]` — prospective entries with a parseable `due:`,
  soonest first. `--within` bounds the window (`14d` or a bare integer); an
  already-overdue entry always shows regardless of the window, because it is
  definitionally due. Unparseable dates are `triage`'s problem (`invalid-due`)
  and are silently skipped here rather than duplicating that check.
- The same report as an MCP tool, `due`, alongside `triage`/`status`.
- `.github/workflows/kb-due.yml` — daily cron, opens/updates/closes one
  running tracking issue ("Knowledge base: entries coming due") via `gh issue
  create/edit/close`. Deliberately one checklist issue, not one issue per
  entry: three prospective entries exist in the store today, and a
  per-entry issue would be more process than the problem. Formatting is
  split into `scripts/kb_due_issue.py` (`due.json` → title + body, a pure
  function, unit tested) so the untestable half — the actual `gh` calls — is
  a thin, readable shell script rather than logic worth testing badly.

**What was not tested, and why the confidence is `high` not `verified`.**
Nothing in this environment can fire a scheduled GitHub Action, so
`kb-due.yml` itself has never actually run — only `kb.py due` and
`kb_due_issue.render`/`main` are unit tested (18 new tests). Re-verify this
entry after the workflow's first real fire confirms the issue gets created,
updated on a second run, and closed when the queue empties.

See [[kb-roadmap]] for where this sits among the ten phases, and
[[kb-entry-status-model]]/[[kb-over-mcp]] for the `triage`/`status`/MCP
conventions this follows.
