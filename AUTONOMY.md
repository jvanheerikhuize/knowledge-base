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

- [x] **Probe sibling-repo access.** (2026-07-28) **No.** Routine sessions are
  scoped to the one repo the routine was configured with; a sibling clone fails
  on auth and the GitHub MCP tools refuse other repos. All work stays here.
  Recorded as `sibling-repo-access-denied-in-routines`. To get autonomous work
  in another repo, configure a separate routine pointed at it.
- [x] **ROADMAP Phase 2 — expose the KB over MCP.** (2026-07-28) Designed and
  shipped: `scripts/mcp_server.py`, stdio, stdlib-only, six tools plus entries
  as resources, writes staged and never committed, `--read-only` mode. Speaks
  MCP 2025-11-25; the version trade-off against 2026-07-28 is written up in the
  ROADMAP. 39 new tests.
- [x] **Real source URLs in ROADMAP.md.** (2026-07-28) Partly: a "Sources
  consulted" section now lists what was actually read, with dates. The
  near-neighbour projects named in Phase 2 are flagged as still unverified
  rather than dressed up with plausible links — verify or drop them.
- [x] **Test consolidation & audit.** (2026-07-29) Done. Read all 231 tests
  against the four source files they cover. Consolidation was the smaller
  win: trimmed a handful of tests re-asserting numbers already pinned
  elsewhere, merged one strict-subset test, repurposed one confidence-decay
  test whose two ages landed on the same clamp branch into a new
  intermediate-step test. The gap half mattered more: it found two real,
  silent bugs — `kb.py set <name> links <value>` wrote a bare string instead
  of list syntax (frontmatter corruption, since e.g. `cmd_link` then iterates
  the string's characters), and `kb.py dupes` had no archived-entry filter
  where `kb.py candidates` did, so an archived entry could be flagged as a
  live duplicate. Both fixed (`set` now refuses `links`, pointing at `kb.py
  link`; `dupe_pairs` now skips archived entries like `_candidate_docs`
  does), each with a regression test confirmed to fail pre-fix. Also added
  tests for previously-uncovered error paths (MCP `propose_update`/`judge`
  on a missing entry, malformed JSON-RPC params/method/`resources/read`,
  `build_site`'s empty-KB rendering branches, `serve.py` malformed POST
  bodies and a route missing its required name). 231 → 244 tests, all green.
  Write-up: `kb-test-audit-2026-07-29`.
- [ ] **KB hygiene pass.** `scripts/kb.py triage`; re-verify ageing entries,
  connect isolated ones, act on overdue prospective entries.
- [ ] **Site polish.** Review the published site (GitHub Pages) for anything
  broken or stale; regenerate if the store changed.
- [x] **ROADMAP Phase 3 — semantic duplicates.** (2026-07-29) Done, and the
  2026-07-28 negative result was too broad. The failure was the **global
  threshold**, not the metric: re-measured against seven planted paraphrases,
  per-entry nearest neighbours unioned both ways caught 7 of 7 in 5% of the pair
  space, where global ranking put the worst at #81 of 378. Shipped `kb.py
  candidates` (blocks, refuses to rule) + `kb.py judge` (durable verdicts in
  `.kb/verdicts.json`, bound to a content digest) + both over MCP. First full
  pass: 42 pairs judged, zero duplicates, one missing link found. Write-up:
  `kb-duplicate-candidates-by-nearest-neighbour`.
- [ ] **ROADMAP Phase 3 — `consolidate` and contradiction detection.** Now
  unblocked: `candidates` supplies the candidate set and `judge` records which
  pairs are real, so `consolidate` has a queue (pairs standing at `duplicate`).
  The first pass found none, so wait for a real merge to design against rather
  than a hypothetical one — the nearest case is `distill-session-into-memory`
  against `persist-insight-to-knowledge-base`, judged `overlap` because the
  latter's steps 3–5 restate most of the former. Contradiction detection is the
  other half and is still mechanical-first: same subject, conflicting
  frontmatter, or a body that negates one it links to.
  (The 2026-07-28 warning still stands and now lives with the code: **do not
  lower the `dupes` threshold to "catch more"** — that is a different command
  from `candidates`, its regression test will fail, and the next thing it finds
  is a false positive.)
- [ ] ~~**Workspace docs drift**~~ — **blocked, do not re-attempt from a
  routine.** Needs sibling-repo access, which routine sessions do not have
  (see `sibling-repo-access-denied-in-routines`). Reconciling `~/Repos/CLAUDE.md`
  needs either a local session or a routine configured against that repo.

## Debrief contract

`DEBRIEF.md` is the single triage document Jerry reads on return. Every shipped
change is one unchecked checkbox with date and commit/PR ref. Jerry marks only
what he **doesn't** want; everything unmarked stands. Keep entries one line,
self-contained, newest last.
