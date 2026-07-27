# AUTONOMY.md — Charter for autonomous holiday sessions

**Mandate holder:** Jerry (jvanheerikhuize), given in chat on 2026-07-27.
**Period:** 2026-07-28 through 2026-08-05 (Jerry returns Wednesday 2026-08-05).
**Executor:** scheduled Claude Code cloud sessions (claude.ai Routines) plus any
local sessions Jerry starts. If you are reading this inside a routine run, this
file is your contract — follow it without asking for input.

## Mission

Make the workspace repos as **LEAN and advanced** as possible. Research, update
roadmaps, consolidate tests, build features, audit, clean up. Prefer
consolidation and deletion over addition. Make your own decisions; do not stop.

## Session protocol

1. `scripts/kb.py context "autonomous holiday work"` and `scripts/kb.py triage`
   for background; read `memory/AGENT.md` if you haven't.
2. Pick the **top unchecked item** in the backlog below. One focused piece of
   work, completed end to end, beats three started.
3. Before pushing: `python3 -m unittest discover -s tests -q` and
   `scripts/kb.py lint` must pass (when the change touches this repo).
4. Mark the backlog item done here (or split it and record progress), so the
   next session doesn't repeat it.
5. Record every shipped change in `DEBRIEF.md` (format described there).
6. Persist durable new insight as KB entries (`scripts/kb.py new`), honest
   confidence, linked into the graph.

## Git strategy (authorized by Jerry, 2026-07-27)

- **Small fixes** → commit and push immediately.
- **Logical pieces of work** → push directly to a work branch.
- **Large chunks** → branch + PR, then **merge the PR yourself** ("automerge"
  is explicitly pre-authorized). Delete merged branches.
- Conventional-commit messages, small focused commits.
- Never force-push. Never rewrite history on main.

## Model tiering

Research / design / roadmap work → higher-tier model (Opus routine or explicit
choice). Execution of well-defined items → lower tier (Sonnet). Routines are
already configured this way; inside a session just do the work you were given.

## Guardrails

- Tests green before every push; if you can't get them green, push nothing and
  record the blocker in `DEBRIEF.md`.
- Do not touch credentials, secrets, or account/security settings.
- Do not delete data outside the repos; repo-internal cleanup is in scope.
- If the same step fails twice, stop that item, record the blocker in
  `DEBRIEF.md`, and move to the next backlog item.
- Scope may be increased when needed (Jerry: "increase your scope if you need
  to"), but record any scope expansion in `DEBRIEF.md`.

## Backlog (top item first — keep this list current)

- [ ] **Probe sibling-repo access.** From a routine session, check whether
  other `jvanheerikhuize/*` repos can be cloned/pushed (try `gh repo clone` /
  `git clone`). Record the result as a KB entry. If yes, expand this backlog
  with per-repo items from the workspace ROADMAP (P2 knowledge consolidation
  is next); if no, all work stays in this repo.
- [ ] **ROADMAP Phase 2 — expose the KB over MCP.** Design first (research
  session), then implement stdlib-only if feasible; otherwise document the
  chosen approach in the ROADMAP with real trade-offs.
- [ ] **Real source URLs in ROADMAP.md.** Replace placeholder references with
  the actual sources consulted.
- [ ] **Test consolidation & audit.** Review `tests/` for overlap and gaps
  (127 tests as of 2026-07-27); consolidate where LEAN, add coverage where a
  regression could hide.
- [ ] **KB hygiene pass.** `scripts/kb.py triage`; re-verify ageing entries,
  connect isolated ones, act on overdue prospective entries.
- [ ] **Site polish.** Review the published site (GitHub Pages) for anything
  broken or stale; regenerate if the store changed.
- [ ] **Workspace docs drift** (needs sibling access): `~/Repos/CLAUDE.md`
  lists 20 repos, disk has 22 — reconcile the table (see KB entry
  `workspace-repo-inventory-drift`).

## Debrief contract

`DEBRIEF.md` is the single triage document Jerry reads on return. Every shipped
change is one unchecked checkbox with date and commit/PR ref. Jerry marks only
what he **doesn't** want; everything unmarked stands. Keep entries one line,
self-contained, newest last.
