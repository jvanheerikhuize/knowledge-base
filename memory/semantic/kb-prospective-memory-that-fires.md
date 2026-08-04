---
name: kb-prospective-memory-that-fires
type: semantic
description: kb.py due (CLI + MCP) plus a daily kb-due.yml workflow surface a prospective entry's due date before it lapses, not just after
confidence: verified
source: ROADMAP.md Phase 5, shipped 2026-08-01; workflow behavior confirmed against three real fires, 2026-08-02 through 2026-08-04
created: 2026-08-01
last_verified: 2026-08-04
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

**Confirmed against three real fires (2026-08-02, 08-03, 08-04).** The daily
cron has now run three times (run IDs 30739850195, 30803269519, 30893134216,
all `conclusion: success`), and issue #36 shows exactly the lifecycle the
entry predicted: created on the first run with `holiday-autonomy-mandate`
listed at "in 3d", left open and its body rewritten on each subsequent run as
the countdown ticked down ("in 2d", then "in 1d") rather than opening a
duplicate issue or going stale. `gh issue list --search` correctly found the
existing open issue by title on every run, so the create-vs-edit branch
picked the right side each time.

**Still unconfirmed: the close path.** `holiday-autonomy-mandate` is due
2026-08-05 and hasn't cleared yet, so the "close issue when nothing is due"
branch (`kb-due.yml` lines 51–56) has not fired in production — only its
render-side unit test has exercised an empty queue. Confidence is `verified`
for the create/update behavior, which is the entry's core claim ("surface a
due date before it lapses"); the close branch is simple enough (one `gh issue
close` guarded by `count == 0`) that a future session should just watch for it
rather than re-open this entry to chase it.

See [[kb-roadmap]] for where this sits among the ten phases, and
[[kb-entry-status-model]]/[[kb-over-mcp]] for the `triage`/`status`/MCP
conventions this follows.
