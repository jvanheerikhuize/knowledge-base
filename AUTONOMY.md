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
- **End every session with the work on `main`, or with the reason it is not
  written in `DEBRIEF.md`.** A branch that is pushed and left is invisible: it
  is not reviewed, its backlog item still reads unchecked, and the next session
  redoes it. This is not hypothetical — the 11:00 routine did exactly that on
  2026-07-29 and 2026-07-30 (`claude/cool-cerf-so8mrh`,
  `claude/cool-cerf-sr8tim`), including three bug fixes and a debrief line that
  never reached `main`. Pushing to a branch is a checkpoint, not an ending.
- **Before picking a backlog item, check `git ls-remote --heads origin`.** An
  unmerged `claude/*` branch may already hold the work.
  **Two exceptions, already dealt with:** `claude/cool-cerf-so8mrh` and
  `claude/cool-cerf-sr8tim` were fully recovered into `main` on 2026-07-31
  (PR #30) and hold nothing new. They still appear in `ls-remote` because a
  routine session cannot delete a remote branch — the git relay rejects the
  delete and the GitHub MCP tools have no delete-branch call — so Jerry has to
  remove them. Ignore them; do not re-merge them.

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
- [x] **Test consolidation & audit.** Done **twice**, 2026-07-29 and
  2026-07-30, because the first pass was pushed to a branch and never merged,
  so this box still read unchecked when the second session picked it up. Both
  passes are kept below — they found different bugs, so the duplicated effort
  was not wasted, but it was still duplicated. This is the case that put the
  "end every session with the work on `main`" rule in the git strategy above.

  *Pass 1 (2026-07-29, 231 tests read).* Consolidation was the smaller win:
  trimmed a handful of tests re-asserting numbers already pinned elsewhere,
  merged one strict-subset test, repurposed a confidence-decay test whose two
  ages landed on the same clamp branch into a new intermediate-step test. The
  gap half found two real, silent bugs — `kb.py set <name> links <value>`
  wrote a bare string instead of list syntax (frontmatter corruption, since
  `cmd_link` then iterates the string's characters), and `kb.py dupes` had no
  archived-entry filter where `kb.py candidates` did, so an archived entry
  could be flagged as a live duplicate. Both fixed with regression tests
  confirmed to fail pre-fix, plus coverage for previously-unexercised error
  paths (MCP `propose_update`/`judge` on a missing entry, malformed JSON-RPC
  params/method/`resources/read`, `build_site`'s empty-KB branches,
  `serve.py` malformed POST bodies). Write-up: `kb-test-audit-2026-07-29`.

  *Pass 2 (2026-07-30, all four suites re-read).* Found overlap minimal —
  CLI-vs-MCP layering is intentional, not duplication. The gap sweep found a
  third bug: `cmd_rm`'s referrer scan (`for t, other in iter_entries()`)
  shadowed the outer `t` already resolved to the deleted entry's own type, so
  the log line written after the loop recorded whichever type `iter_entries()`
  last yielded — invisible because every existing `rm` test used a
  single-type store. Fixed, with a mixed-type regression test. Also covered
  `context --limit` and `README.md`/`*.template.md` inside a type folder.
  Write-up: `audit-test-corpora-for-artificial-uniformity`.
- [x] **KB hygiene pass.** (2026-07-31) Audited, nothing to act on: `triage`
  reports clean and `status` shows all 26 entries `current` — none stale,
  isolated, overdue, or unverified past 30 days. The store has stayed this
  clean because the consolidation/contradiction work earlier in the week
  (`judge`, `consolidate`) already forces re-verification and linking as a
  side effect of normal use, so a standalone hygiene pass had nothing left to
  do. No entries changed; nothing to write up.
- [x] **Site polish.** (2026-07-31) Reviewed: `build_site.py` output has zero
  broken internal links (checked all 31 generated pages programmatically),
  no unresolved `[[wikilink]]` markup in rendered bodies, dark-mode CSS and a
  responsive viewport meta tag are both present, and `data.json`'s entry
  count (26) matches the index. The live GitHub Pages URL itself could not be
  fetched from this session — this environment's network policy returns 403
  on `jvanheerikhuize.github.io` (confirmed via the proxy status endpoint,
  not a transient error) — so this was verified against a local build plus
  the Pages workflow's run history instead: the last `pages.yml` deploy
  (2026-07-31T08:08Z) succeeded, and no commit touching `memory/**` or
  `.kb/**` has landed since, so the published site matches the store as of
  this pass. Nothing broken found; nothing regenerated because nothing was
  stale.
- [x] **ROADMAP Phase 3 — semantic duplicates.** (2026-07-29) Done, and the
  2026-07-28 negative result was too broad. The failure was the **global
  threshold**, not the metric: re-measured against seven planted paraphrases,
  per-entry nearest neighbours unioned both ways caught 7 of 7 in 5% of the pair
  space, where global ranking put the worst at #81 of 378. Shipped `kb.py
  candidates` (blocks, refuses to rule) + `kb.py judge` (durable verdicts in
  `.kb/verdicts.json`, bound to a content digest) + both over MCP. First full
  pass: 42 pairs judged, zero duplicates, one missing link found. Write-up:
  `kb-duplicate-candidates-by-nearest-neighbour`.
- [x] **ROADMAP Phase 3 — contradiction detection.** (2026-07-30) Done, and
  the mechanical version this backlog proposed does not work. Nine
  contradictions planted (eight written, one recovered from git): negation
  polarity caught 5 of 9 and is blind to competing *positive* assertions ("20
  repos" vs "22 repos"); claim-level alignment caught 4 of 9. The blocker
  already shipped for duplicates caught 8 of 9 at `-n 3` and 9 of 9 at `-n 5`.
  So no detector — `judge` gained `--agreement agree|contradict`, an axis
  independent of `duplicate|overlap|distinct`, plus the `contradicted` status
  above `broken` and a `contradiction` triage reason. Omitting the axis stores
  no key, so the 46 older verdicts reopened as *unexamined*. First pass: 75
  pairs at `-n 5`, **one real contradiction** (`kb-entry-status-model` claiming
  eight statuses against `kb-forgetting-model` describing a ninth), standing
  two days through a clean lint and a clean triage. Reconciled. Write-up:
  `kb-contradiction-is-a-second-axis`. 36 new tests (267 total).
- [x] **ROADMAP Phase 3 — `consolidate`.** (2026-07-31) Done, and waiting for a
  merge was waiting for the wrong thing. 87 verdicts, **zero duplicates** — a
  curated store accumulates `overlap`, not duplicates, so a merge-only
  `consolidate` was dead code. The live defect was in the overlap bucket:
  `judge` recommends a link once and nothing ever checks it happened, and
  **seven** overlapping pairs had no edge — invisible to lint, which reads one
  entry at a time while a missing edge is a property of a pair. Shipped as
  three queues of proposals (unmerged duplicates, missing edges, restated
  passages). The passage signal was measured first: shingle containment 1 of 7,
  passage-as-BM25-query 7 of 7, narrowed to 28 of 2728 pairs by requiring it to
  beat its own host with the passage removed. 38 new tests (305 total).
  Write-up: `kb-consolidation-is-owed-work`. Phase 3 is now closed.
  (The 2026-07-28 warning still stands and now lives with the code: **do not
  lower the `dupes` threshold to "catch more"** — that is a different command
  from `candidates`, its regression test will fail, and the next thing it finds
  is a false positive.)
- [x] **ROADMAP Phase 4 — temporal validity.** (2026-08-01) Done, and the two
  frontmatter fields it proposed have an empty domain. Replayed every commit
  that has ever touched `memory/` and classified every change (38 creations, 30
  bookkeeping-only, 22 rewrites, 6 appends, 3 deletions — all three of generated
  files, never an entry): **0 of 26** entries have a claim with a knowable
  expiry date, and **0 of 22** rewrites retired a whole entry. The mechanism is
  the finding — obsolescence is repaired *by the change that causes it, in the
  same commit* (`1d1c713` deletes `scripts/visualize.py` and rewrites all four
  entries citing it; `9dcde20` moves the tree and fixes both citers), so there
  is never an interval for a validity interval to describe. The stronger
  "bind validity to a source, not a date" framing was tested too and failed
  harder: replayed across all 21 commits it fired **244 times with 0 true
  positives**, and all 16 of its standing fires today are correct citations —
  sibling repos, a gitignored build output, and an entry that cites two missing
  scripts *because its subject is that they are missing*. Shipped instead:
  `kb.py history <name>`, since correction-in-place means the superseded wording
  of a claim lives only in git. It labels each revision by what it changed
  (claim / body / bookkeeping) because `verify` and `link` touch an entry far
  more often than an author does. Small but real: 2 of 26 entries have had a
  claim rewritten, and the need was already felt twice with no tool to meet it.
  Not on the site — `actions/checkout` is depth-1, which would render every
  entry as never having changed. 13 new tests (334 total). Write-up:
  `kb-corrections-happen-in-place`.
- [x] **ROADMAP Phase 5 — prospective memory that fires.** (2026-08-01) Both
  bullets shipped as designed, no negative result this time. `kb.py due
  [--within Nd]` (CLI + MCP tool) surfaces a prospective entry's due date
  before it lapses; `.github/workflows/kb-due.yml` (daily cron) opens,
  updates, and closes a single tracking issue via `gh issue`, with the
  formatting split into `scripts/kb_due_issue.py` so the testable half (title
  + body rendering) is unit tested and the untestable half (the actual `gh`
  calls — nothing in this environment can fire a scheduled Action) stays a
  thin, readable shell script. 18 new tests (353 total), lint and triage
  clean, one KB entry (`kb-prospective-memory-that-fires`, `confidence: high`
  pending the workflow's first real fire). ROADMAP Phase 5 closed. Write-up:
  `kb-prospective-memory-that-fires`.
- [ ] ~~**Workspace docs drift**~~ — **blocked, do not re-attempt from a
  routine.** Needs sibling-repo access, which routine sessions do not have
  (see `sibling-repo-access-denied-in-routines`). Reconciling `~/Repos/CLAUDE.md`
  needs either a local session or a routine configured against that repo.

## Debrief contract

`DEBRIEF.md` is the single triage document Jerry reads on return. Every shipped
change is one unchecked checkbox with date and commit/PR ref. Jerry marks only
what he **doesn't** want; everything unmarked stands. Keep entries one line,
self-contained, newest last.
