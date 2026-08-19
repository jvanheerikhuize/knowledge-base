# Roadmap

What this knowledge base should grow into, and why. Every item below is scoped
to the constraints that define the project ([[kb-is-file-based]]): markdown
files with YAML frontmatter, stdlib-only Python, git as the only durable write
path, no database, no vector store, no service to keep running.

The organising idea comes from how agent memory is described in current
practice — a lifecycle of **formation → evolution → retrieval**, where the
interesting engineering is not in writing memories down but in consolidating,
ageing, and selecting them. This repo is strong at formation (templates, `new`,
schema lint) and weak at the other two. The roadmap is ordered accordingly.

Status legend: `done` · `next` · `planned` · `someday`

---

## Phase 1 — Retrieval that ranks · `done`

**Gap.** `kb.py search` was an unranked substring match over body plus
frontmatter values. Every hit was equal, and the caller sorted by hand. The
success metric in [PURPOSE.md](PURPOSE.md) is that an agent can "retrieve
relevant facts at inference time" — unranked grep does not meet that once the
store passes a few dozen entries.

- ✅ **BM25 ranking in `search`.** Classic BM25 is ~40 lines of stdlib; the corpus
  is small enough that scoring every entry per query is free. Ranked output,
  `--limit`, and a score column.
- ✅ **Type-aware scoring.** Recency is a first-class signal for `episodic` (what
  happened most recently usually wins); content similarity is the right signal
  for `semantic`. Keep episodic logs out of the semantic ranking by default so
  a busy week of events cannot bury a durable fact.
- ✅ **`kb.py context "<task>" [--budget N]`.** Emit a paste-ready context pack:
  the top-ranked entries, trimmed to a token budget, with provenance. This is
  the single command an agent should need at the start of a task, and it is the
  literal shape of the success metric.

## Phase 2 — Expose the KB over MCP · `done`

**Gap.** Every consumer had to shell out to `kb.py` and parse text. The
near-neighbour projects that were re-checked ([Basic Memory](https://basicmemory.com/),
brain.md — see Sources consulted) have converged on the same answer: serve the
store over MCP so any agent can use it as a tool.

- ✅ `scripts/mcp_server.py`, stdio JSON-RPC, stdlib-only — the same dependency
  posture as the rest of the tooling. Tools call kb.py's *library* functions,
  never its `cmd_*` handlers, because the stdio transport forbids anything on
  stdout that is not an MCP message and those handlers print.
- ✅ Tools: `context`, `search`, `get`, `triage`, `status`, `propose_update`.
  Entries are also published as resources under `kb://entry/<name>`, which is
  the MCP-native way to hand an agent a document it can attach directly.
- ✅ **Writes are proposals.** `propose_update` stages a change in the working
  tree and never commits, mirroring `scripts/serve.py`. Git stays the durable
  write path and the review gate, per [[editing-the-kb-without-a-cms]].
  `--read-only` drops the tool from `tools/list` altogether.

**The version decision, and what is left.** The server speaks `2025-11-25` and
negotiates down to `2025-06-18` / `2025-03-26`. It deliberately does not
implement `2026-07-28`, which landed the day this shipped: that revision deletes
the `initialize` handshake in favour of per-request `_meta`, adds `server/discover`,
and states outright that there is no automatic compatibility with `2025-11-25`.
Implementing a spec no client speaks yet, against SDKs still inside their
ten-week validation window, would trade a working server for a hypothetical one.

- **Open:** re-evaluate `2026-07-28` once the reference SDKs and at least one
  client ship it. The handshake removal is the only structural change that
  touches this server — the tool and resource surfaces are unaffected — so the
  migration is a lifecycle change, not a rewrite.

## Phase 3 — Consolidation and forgetting · `done`

**Gap.** `memory/AGENT.md` stated plainly that lint "does not detect
content-level contradictions between entries — no such checker exists yet."
Nothing merged duplicates, nothing aged, nothing retired. The documented
failure mode of memory systems is exactly this: stale contradictory facts
outranking current ones until an agent that remembers everything remembers
nothing useful.

- ✅ **`kb.py dupes`** — shipped, but **not** doing what this line originally
  promised, and the gap is the finding. Shingling was measured against a
  hand-written paraphrase of an existing entry: it ranked **#14 of 210 pairs**,
  below thirteen pairs of entries that merely share a subject. On raw 5-word
  shingles it scored 0.000. Lexical similarity ranks topical neighbours above
  actual restatements on hand-written prose, so any threshold low enough to
  catch a paraphrase admits a dozen false positives first.

  So `dupes` is scoped honestly to **near-verbatim** overlap — an entry
  recorded twice, a scaffolded copy drifting back, an agent re-adding its own
  work — at a threshold ~70× the store's observed maximum, and it prints the
  sentence naming its own limit so a clean result is never read as "no
  duplicates". It also reports *containment*, which catches the asymmetric case
  Jaccard scores lowest: a short entry wholly absorbed into a longer one.
  MinHash/LSH were rejected as approximations of a computation that is free at
  this scale. Full write-up: [[kb-duplicate-detection-limits]].

- ✅ **Semantic duplicate detection** — `kb.py candidates` + `kb.py judge`, and
  the interesting part is why it works after the previous attempt failed.

  The earlier measurement was right about what it measured and wrong about what
  that implied. It asked whether a lexical score can *decide* a pair, found it
  cannot, and concluded lexical similarity was the wrong signal. But the failure
  was in the framing: a **global threshold** asks "is this pair similar in
  absolute terms", and absolute similarity is dominated by how much vocabulary a
  *topic* happens to share — which varies far more between topics than
  duplication does within one. Asking instead "of everything here, which entries
  is this one **most** like" cancels that per-entry baseline out.

  Re-measured against seven hand-written paraphrases planted in this store
  (28 entries, 378 pairs): as a global ranking the worst positive sat at **#81 of
  378**; as each entry's single nearest neighbour, unioned in both directions,
  **all seven** were caught inside **19 pairs** — 5% of the space. The union is
  load-bearing, not a detail: it is what took 6 of 7 to 7 of 7 for free, because
  a long entry's nearest neighbour is often not the short entry restating it
  while the reverse holds reliably.

  So the shipped thing is a **blocker** — the recall half of the standard
  record-linkage pair — and it refuses to rule. An agent reads the pair and
  rules, which is the same division of labour as `kb.py new` and keeps the
  no-vendor-model rule of [[twin-sovereignty-constraint]] intact. `judge` writes
  the verdict to `.kb/verdicts.json` bound to a digest of both entries' claim
  text, so re-verifying or relinking does not expire it but rewriting a body
  does. That is what makes the pass incremental: the first sweep of this store
  cost 42 judgements; a new entry costs about `n` more, not another full sweep.

  First full pass, 2026-07-29: 42 pairs judged, **no duplicates** — 24 overlap,
  18 distinct — and one unlinked overlap found and linked
  (`kb-agent-entrypoint-is-agent-md` ↔ `workspace-repo-inventory-drift`).
  Write-up: [[kb-duplicate-candidates-by-nearest-neighbour]].

- ✅ **`kb.py consolidate`** — shipped, and the queue this line named is not the
  one that had anything in it.

  This item was scoped as "propose merges", working from the pairs standing at
  `duplicate`. Measured against the store's own ledger, that queue is empty and
  structurally likely to stay empty: **87 verdicts across two full passes, zero
  duplicates**, 44 `overlap`, 43 `distinct`. A store curated by an agent that
  judges pairs as it writes them does not accumulate duplicates. It accumulates
  overlap.

  The defect was inside that overlap bucket, and it is one nothing else could
  see. `judge` prints "link them if they are not linked yet" once, when the
  verdict is passed — and then the pair settles and drops out of `candidates`
  forever, so the advice is given exactly once and never checked. **Seven of
  the 44 overlapping pairs had no edge between them.** `lint` cannot find that:
  it checks links that point nowhere and entries nobody links to, and both are
  properties of a *single* entry. A missing edge between two well-connected
  entries is a property of a **pair**, and only the ledger knows the pair is
  real. All seven were genuine; all seven are now drawn.

  So `consolidate` reads the ledger and reports what each standing verdict
  still owes, in three queues — unmerged duplicates, overlapping pairs with no
  link, and restated passages. It proposes and never rewrites, for the same
  reason `candidates` refuses to rule.

- ✅ **Sub-entry consolidation** — the "distil repeated observations into one
  fact" half, which needed its own measurement and its own metric.

  Seven hand-written restatements were planted in a copy of the store, each a
  paragraph in one entry restating a *different* entry's claim in different
  words. Over 2728 (passage, entry) pairs:

  | signal | pairs it puts up | caught |
  |---|---|---|
  | passage shingle-containment, best entry | 20 (0.7%) | 1 of 7 |
  | passage as a BM25 *query*, best entry | 124 (4.5%) | **7 of 7** |
  | …that also beats its own host, passage removed | 72 (2.6%) | **7 of 7** |
  | …and clears a 1.5× margin over the runner-up | **28 (1.0%)** | **7 of 7** |

  Containment fails one level down for exactly the reason it failed at
  whole-entry scale in [[kb-duplicate-detection-limits]]: shingles measure
  shared *phrasing*, and a restatement is precisely what shares none. Asking
  "of everything here, which entry is this paragraph most like" is the framing
  that rescued duplicate detection, applied to passages.

  The host filter is the new part and it is what makes the queue readable: a
  passage is only interesting if it scores higher against another entry than
  against **its own entry with that passage removed** — a paragraph more at
  home somewhere else than where it is written. Removal is load-bearing; leave
  the passage in and its host wins trivially, every time.

  **What the margin costs, stated plainly.** The default 1.5 holds the planted
  set at 7 of 7, but it drops the one real case this store already knew about:
  `persist-insight-to-knowledge-base` steps 3–5 restating
  `distill-session-into-memory`. Those steps *are* found — they beat their own
  host — but the runner-up is close, because procedure steps share vocabulary
  (`kb.py new`, lint, triage) with half the store while distinctive prose does
  not. `--margin 1.0` surfaces them, at 63 passages to read instead of 22. The
  planted positives were topical prose and the default is tuned to them; that
  is a real limit, not a rounding error.

  First full pass, 2026-07-31: 22 proposals read, **two acted on**. `kb-roadmap`
  was retelling the entire contradiction-detection finding that
  [[kb-contradiction-is-a-second-axis]] exists to hold — cut to what it
  uniquely knows plus the link. And the `persist`/`distill` case above, found
  at `--margin 1.0`: the restated steps went, and the one thing they added (the
  verified-vs-`high` rubric) moved into `distill`'s step 3, where the procedure
  lives. The other 20 are an entry legitimately discussing its neighbour, which
  is what a blocker is supposed to produce.

  Rewriting those three entries expired 26 verdicts — the design working, not a
  cost to route around: a judgement is bound to the text it was passed on.
- ✅ **Contradiction detection** — shipped as `judge --agreement`, and the
  finding is that the mechanical version this line proposed does not work.

  Nine contradictions were planted in a copy of the store — eight hand-written,
  one real, recovered from git (the pre-correction
  [[kb-duplicate-detection-limits]] against the entry that overturned it) — and
  every cheap signal was scored against them.

  | signal | pairs it puts up | caught |
  |---|---|---|
  | global topical similarity | positives at #2 to #107 of 435 | no usable cut |
  | claim-level sentence alignment | 10 pairs (2%) | 4 of 9 |
  | negation-polarity mismatch | 12 pairs (3%) | 5 of 9 |
  | the existing `candidates` blocker, `-n 3` | 62 pairs (14%) | **8 of 9** |
  | the existing `candidates` blocker, `-n 5` | 103 pairs (24%) | **9 of 9** |

  "An entry whose body negates one it links to" is the polarity row, and it
  cannot see the commonest shape of disagreement at all: two competing
  *positive* assertions, "20 repos" against "22 repos", with no negation on
  either side. Its false positives are negation-scope errors and entries that
  agree *about* a contradiction elsewhere.

  So no detector shipped. The blocker built for semantic duplicates already
  surfaces these pairs; what was missing was that `duplicate|overlap|distinct`
  has no value meaning "these disagree", so a pair could be judged, look
  settled, and never have been asked. `--agreement agree|contradict` is a
  second, independent axis on the same verdict — a pair can restate *and*
  disagree — and omitting it stores no key, so the 46 verdicts written before
  it existed read as unexamined rather than as fine. Standing contradictions
  are the `contradiction` triage reason and the `contradicted` status, above
  `broken`, and deliberately not a lint failure: lint checks form.

  Duplication is a whole-entry relation and contradiction a sub-claim one,
  which is why full recall wants `-n 5` here where 5% of the pair space
  sufficed for paraphrases. First full pass 2026-07-30: 75 pairs at `-n 5`,
  **one real contradiction** — [[kb-entry-status-model]] claiming eight
  statuses against [[kb-forgetting-model]] describing a ninth — standing for
  two days through a duplicate-judging pass, a clean lint, and a clean triage,
  because nothing had asked. Reconciled; the store is clean on both axes.
  Write-up: [[kb-contradiction-is-a-second-axis]].
- ✅ **`kb.py archive <name>`** — invalidate rather than delete. Archived entries
  leave the retrieval set (search, context packs, triage) but stay readable,
  stay linked, and stay in the graph, so the audit trail survives. `status`
  accounts for them under an `archived` state; `--undo` reverses it; deletion
  remains available via `rm`.
- ✅ **Confidence decay** — `last_verified` ageing now demotes confidence in
  ranking rather than only printing a warning: one level per staleness period,
  so a `verified` fact untouched for a year is not verified. Applied at read
  time and reversed by `verify`, so the file keeps the level its author
  recorded — decay is never a silent rewrite. Both numbers are surfaced
  wherever they differ, including in context packs, because a claim's age is
  part of its provenance.

**Why the forgetting half shipped first.** Decay and archiving are decisions
about a *single* entry and cannot really be wrong. Merging is a claim about a
*pair*, and the measurement above shows how hard that claim is to make from text
alone. That ordering turned out to be right for a reason that was not obvious
when it was chosen.

**And the lesson from getting the pair half wrong once.** The negative result
was real, reproducible, and correctly guarded by a regression test — and it
still pointed at the wrong conclusion, because the experiment tested a metric
when the thing that was broken was the question being asked of it. Before
accepting "X cannot work", check whether what was measured was X or one framing
of X. The regression test that pinned the old finding
(`test_a_paraphrase_is_not_flagged`) is still passing and still correct: the
paraphrase must not be reported as a near-verbatim *duplicate*. It is now
reported as a *candidate*, which is a different claim, by a different command.

## Phase 4 — Temporal validity · `done`

**Gap, as originally written.** An entry is either true or deleted; there is no
way to say "this was true until March." The proposal was `valid_until` and
`supersedes: <name>` in frontmatter, retrieval skipping expired entries, and the
site rendering them as historical — so that "recency wins, and you can see
exactly what it won against."

The last clause was the real requirement. Neither of the two fields serves it,
and the store's own history says so.

**What was measured.** Every commit that has ever touched `memory/` was
replayed and every change to an entry classified: 38 creations, 30
bookkeeping-only revisions, 22 rewrites, 6 appends, 3 deletions (all three of
generated files or a template that moved, never an entry).

| the proposal | what the history shows |
|---|---|
| `valid_until` — a date after which a claim lapses | **0 of 26** entries have a claim with a knowable expiry date. Every one of the 22 rewrites was a fact overtaken by an event nobody could have dated: a script deleted, a status added, a file moved. The single date-bound entry, `holiday-autonomy-mandate`, is `prospective` and already carries `due:` |
| `supersedes: <name>` — this entry replaces that one | **0 of 22** rewrites retired a whole entry. The nearest case is the one it was written for: [[kb-duplicate-detection-limits]], whose conclusion was overturned on 2026-07-29. It was deliberately **not** superseded — its measurement and its regression test are still valid and still passing, and only the conclusion moved. `supersedes` would have mismodelled the one case it exists for, because half the entry survived |
| retrieval skips expired entries | nothing to skip |

**The mechanism behind the numbers, which is the finding.** Obsolescence in
this store is repaired *by the change that causes it*, in the same commit. Two
worked examples, both recovered from git rather than assumed:

- `1d1c713` deletes `scripts/visualize.py` **and** rewrites all four entries
  that cited it.
- `9dcde20` deletes `docs/plan.md`, moves `memory/_generated/` to
  `.kb/generated/`, **and** fixes both entries naming the old paths.

The agent that changes the code owns the memory about the code and changes both
at once, so there is never an interval in which a claim is stale and unrepaired.
That is what leaves nothing for a validity interval to express.

**A detour worth recording, because it failed.** Before concluding that, the
obvious stronger framing was tested: bind validity to a *source* rather than a
date — 92% of entries cite a repo path, so flag the entry when the path stops
resolving. Replayed across all 21 commits that touched `memory/`, that check
fired **244 times with 0 true positives** — and it never fired on the real
breaks above, because of the same-commit repair. Its 16 standing fires today
are all correct citations: five entries cite *sibling repos* this one cannot
see ([[sibling-repo-access-denied-in-routines]]), `site/data.json` is a build
output under a gitignored path, and
[[kb-agent-entrypoint-is-agent-md]] cites `ci/lint.py` and
`ci/regenerate_graph.py` inside a table **whose subject is that they do not
exist**. An entry about a missing file necessarily names a missing file. File
granularity is no better: "cited file changed since `last_verified`" fires on
38 of 82 references, because almost everything cites `scripts/kb.py`.

- ✅ **`kb.py history <name>`** — shipped instead, and it is what the original
  "see exactly what it won against" asked for. Correction-in-place means the
  superseded wording of a claim exists **only in git**, which no part of the
  tooling could reach. `history` reads it back, labelling every revision by what
  it changed — `claim` / `body` / bookkeeping — because `verify` and `link`
  touch an entry far more often than an author does, and an unlabelled `git log`
  buries the two revisions that matter under the twenty that stamped a date.
  Where the claim changed, the superseded wording is quoted.

  This is a small number honestly stated: **2 of 26** entries have had their
  one-line claim rewritten, and 8 more have body edits under an unchanged claim.
  What justifies the command is not the count but that the need has already been
  felt twice in real work with no tool to meet it — the 2026-07-29 session had
  to correct [[kb-duplicate-detection-limits]] in place and add a link because
  there was no way to *show* the change, and the 2026-07-30 contradiction pass
  recovered a prior version of that same entry from git **by hand** to use as
  test data.

  Read-only, no new frontmatter, no schema change, nothing to keep in sync; on
  the MCP server as a read tool. It degrades honestly — no git, no repository,
  and an uncommitted entry are three different messages.

- **Deliberately not on the published site.** `actions/checkout` defaults to
  `fetch-depth: 1`, so a site build would render every entry as having exactly
  one revision and never having changed — worse than absent. `history` reports
  `shallow: true` and says its history is truncated rather than lying about it.
  Putting revisions on the site means changing the Pages workflow first, which
  belongs with Phase 8's timeline view, not here.

**The general lesson, which is the second time this repo has learned it.**
Phase 3 recorded that a negative result can be real, reproducible, and correctly
tested and still point at the wrong conclusion when what was measured is one
*framing* of the question. This is the mirror image: a roadmap item's stated
**goal** was right and its proposed **mechanism** was wrong, and the mechanism
was specific enough to look like the goal. `consolidate` hit the same thing —
scoped as "propose merges", shipped against a duplicate queue that measurement
showed was empty and structurally likely to stay empty. Three phases running,
the item as written has been the wrong shape and measuring first has been what
found that. Measure the store before building for it.

## Phase 5 — Prospective memory that fires · `done` (2026-08-01)

**Gap.** `prospective/` entries carry `due:` dates that only surface if someone
runs `triage`. The one memory type that is about the future is inert.

Shipped both bullets as planned, plus the MCP tool that consistency with the
rest of the surface implied:

- **`kb.py due [--within Nd]`** — prospective entries whose due date has
  arrived or is approaching, soonest first. Deliberately narrower than
  `triage`: `triage` already reports `overdue` as a problem after the fact,
  and reusing that path would only ever answer "what already lapsed". `due`
  answers "what is coming", which needs its own report (`due_report()` in
  `kb.py`) built the same way as `triage_report`/`status_report` so all three
  agree by construction. `--within 14d` bounds the window; omitting it lists
  every dated entry. An entry already overdue always shows regardless of the
  window — it is, definitionally, due. Also on the MCP server as a read tool
  (`due`), matching `triage`/`status`.
- **`.github/workflows/kb-due.yml`** — daily cron (06:00 UTC), opens, updates,
  or closes a single tracking issue titled "Knowledge base: entries coming
  due" by shelling out to `gh issue create`/`edit`/`close` (the token is the
  workflow's own `github.token`, no secret added). The formatting is split
  into `scripts/kb_due_issue.py` (`due.json` → title + body, pure function,
  unit tested) precisely so the untestable half — the actual GitHub calls —
  is a thin, inspectable shell script rather than logic worth testing badly.
  Idempotent by construction: re-running with nothing new due is a no-op
  (`gh issue edit` on the same body), and the issue self-closes the first run
  after its last entry clears, rather than sitting open forever.

**What this does not do**, left for a later phase if it turns out to matter:
the issue is a single running checklist, not one issue per entry — with three
prospective entries in the store today, a per-entry issue would be more
process than the problem warrants. If the store grows enough that one issue
becomes unreadable, split it then.

18 new tests (353 total): 8 for `due_report`/`cmd_due`, 3 for the MCP tool,
5 for `kb_due_issue.render`/`main`, plus the existing tool-listing test
extended to expect the new tool name. Not exercised anywhere: the workflow
YAML itself — nothing in this environment can run a scheduled GitHub Action,
so `gh issue create/edit/close` are trusted at the shell-script level, not
integration-tested. Worth re-checking after its first real fire.

**Re-checked 2026-08-04, after three real fires.** The cron ran on
2026-08-02, 08-03, and 08-04 (all `success`); issue #36 was created on the
first run and correctly rewritten, not duplicated, on the next two, tracking
`holiday-autonomy-mandate`'s countdown from "in 3d" to "in 1d". The
create/update half is now `verified` on [[kb-prospective-memory-that-fires]].

**Close branch confirmed 2026-08-05.** Archiving the expired
`holiday-autonomy-mandate` emptied the due queue, run #4 saw `count=0`, and
issue #36 was closed with the workflow's own "Nothing due anymore — closing."
comment. That was a `workflow_dispatch`, not a scheduled fire — the trigger
differs, the job does not, so what is verified is the branch and not the cron
that reaches it (the cron itself is separately confirmed by runs 1–3). Nothing
in this workflow is untested any more, and the reopen table below loses its
only row that a routine session could close.

## Phase 6 — Ingestion without ceremony · `done` (2026-08-03)

**Gap, as originally written.** `memory/working/distill.template.md` is filled
in by hand, so capture depends on remembering to capture. The proposal was
`kb.py distill <transcript>` — extract candidate atomic facts from a session
log into staged `confidence: unverified` drafts — plus `kb.py import` to pull
entries back from a scaffolded copy.

The gap is real. The mechanism proposed for it does not exist: **the claim an
entry makes is not present in the material it came from.** Measured three ways
before writing any of it.

### The claim is written, not extracted

The control ran first, because it bounds everything else: take each of the 30
entries and ask whether its own one-line `description` can be recovered from
**its own body** — the most favourable possible corpus, the text the
description was written to summarise.

| corpus a candidate sentence is drawn from | mean coverage of the description | entries with a candidate ≥ 0.5 |
|---|---|---|
| the entry's own body (control, ceiling) | 0.290 | 1 / 30 |
| session material: code + tests only | 0.224 | 2 / 30 |
| session material: ROADMAP/DEBRIEF prose only | 0.297 | 9 / 30 |
| commit message only | 0.269 | 3 / 30 |
| all of the above together | 0.408 | 11 / 30 |

Coverage is the share of the description's content words present in the
best-matching candidate sentence. The control is the finding: **no sentence in
an entry says what the entry says.** A description is a synthesis produced at
write time, and extraction cannot produce it because it is not in there to
extract. The one corpus that does better than the control does so by being
five times larger, and by containing prose — ROADMAP and DEBRIEF paragraphs —
that a *human or agent had already distilled by hand in the same session*.
Extraction "works" exactly where the work was already done.

Ground truth throughout: the 19 commits that created an entry, with the entry
itself excluded from its own session's material.

### What a transcript actually holds

The other half of the proposal is the input. A real Claude Code transcript
(this session's, 275,094 characters over 267 blocks) is:

| | share |
|---|---|
| tool results (file dumps, command output) | 53.3% |
| tool call inputs | 31.4% |
| attachments and system reminders | 10.5% |
| the assistant's own prose | **0.7%** |
| the assistant's reasoning | **0 bytes — `thinking` blocks persist encrypted, content stripped, signature only** |

So `distill <transcript>` would be handed a corpus that is 85% machinery, whose
reasoning is cryptographically unavailable, to look for a claim that is not
written down in it. And the agent that would run it is the same agent that has
the session in context — it does not need extraction; it needs somewhere to put
what it already knows.

### What shipped instead: `kb.py capture`

The deciding is the work, so the tool does the checking. `capture` takes a
claim **you have written**, in your words, and runs the check `memory/AGENT.md`
has always asked an author to do by hand: *which entry does this already
belong to?*

Two numbers set its behaviour, both measured on this store, neither a new
tuned constant:

- **The restatement test transfers.** Scoring the passage as a BM25 query over
  every entry is `restatements()` with the host term dropped, because a claim
  being captured has no host yet. Fed a true restatement (each entry's own
  description handed back in), the top-ranked entry is the source entry
  **30 of 30**, and the existing `RESTATEMENT_MARGIN` of 1.5 over the runner-up
  fires on **29 of 30** — never on the wrong entry. Fed a genuinely new claim
  (each entry held out of the corpus first), the same margin fires on **7 of
  30**, and every one of those 7 names an entry the author had in fact linked
  to. A fire is never noise: it is the entry this claim restates, or the entry
  it belongs next to.
- **Only the top neighbour is prefilled as a link.** Against the 132 hand-set
  links in this store, the top-ranked neighbour of an entry's body is an edge
  its author actually drew **70%** of the time; precision falls to 51% by rank
  3. The rest are printed for the author to add, because a wrong edge is not
  free — `candidates`, `consolidate`, and the graph all read it.

`kb.py capture [file|-|--text]` with `--check` reports and writes nothing;
with `--type` and `--name` it files the passage as a `confidence: unverified`
entry, description defaulted to its first sentence, top neighbour linked; with
`--extend NAME` it appends the passage to an entry that already holds the claim,
which is the whole point of running the check first. Same three modes as the
MCP `capture` tool, staged in the working tree and never committed, like every
other write on that surface.

The backlog's own warning — "the failure mode is a store filling with restated
context" — is what the design turns on. It is not defended by a review gate
bolted onto an extractor; it is defended by making *"you are restating
[[kb-consolidation-is-owed-work]]"* the first thing the tool says.

### `kb.py import`, deliberately not built

Nothing in the workspace has a scaffolded copy that this session can see
(routine sessions reach one repo — [[sibling-repo-access-denied-in-routines]]),
so an import command would ship against a flow with no observed instance, which
is how Phase 3's merge-only `consolidate` nearly became dead code. Copying
entry files back and running `kb.py lint` covers it today. Revive this when a
scaffolded copy exists **and** has diverged; the collision case (same slug,
different content) is the only part worth code, and it should be written
against a real collision rather than an imagined one.

27 new tests (428 total): 17 for `capture` on the CLI, 2 more for capture into
an empty store — its whole premise is comparison, so day one is its own case —
8 over MCP, and the tool-listing test extended. `new` and `capture` now share
`scaffold_entry`,
which raises instead of exiting so the in-process MCP server survives a bad
slug — asserted, since a `sys.exit` there used to take the server down with it.

## Phase 7 — Measure whether the memory is any good · `done` (2026-08-02)

**Gap.** There were 353 tests of the tooling and none of the memory. Nothing
told you whether retrieval got better or worse as the store grew.

Both bullets shipped — `.kb/golden.json` plus `kb.py eval` and
`tests/test_retrieval_golden.py`, and `kb.py stats`. But the measurement that
came first says something the item as written did not anticipate, and it is
the reason the test asserts what it does.

### A golden set is only worth shipping if it can fail

The obvious way to build one is to walk the store and turn each entry into a
query. Measured, that produces a fixture that **cannot fail**. Scoring 28
title-derived queries (`kb-over-mcp` → "kb over mcp") against fourteen
deliberately degraded rankers:

| query set | rankers scoring a perfect 1.000 |
|---|---|
| derived from entry titles | **14 of 14** — including one that never reads an entry body, and one with no term weighting at all |
| derived from entry descriptions | 12 of 14 |
| paraphrases, written as questions | 0 of 14 |

A title-derived set passes for a ranker with no ranking in it. It would have
sat in CI going green for years while measuring the tokenizer. So the fixture
is 28 **task-shaped questions**, written as a question first and only then
matched to the entry that should answer it — "am I allowed to merge my own
pull request while he is away", not "holiday autonomy mandate". The wording is
the entire fixture, and `test_no_query_restates_its_own_entry_title` asserts it
stays that way (no query may reuse more than 60% of the words in its entry's
name; the set's current worst is 50%). Without that guard the natural repair
for a failing query — nudge it toward the entry's vocabulary — silently turns
the suite back into decoration.

### What the set can and cannot see

Against the real store as it stood when the study ran, 28 queries over 28
entries: **success@1 0.536, MRR 0.668, recall@3 0.786, recall@5 0.857.**
`recall@5` is the number that matters most, because `kb.py context` hands back
a handful of entries rather than one. Every ablation below is from that 28/28
run, paired on the same queries.

> **Corrected 2026-08-10 (Phase 13).** That sentence was wrong when it was
> written. `recall@5` is a *rank* metric and the pack is bounded by a *token
> budget*; on 2026-08-02 the default pack already held 3.5 entries, not 5, and
> by 2026-08-09 it held 2.75. `recall_at_pack` now scores what the pack
> actually returns, and the two are separate numbers on purpose.

The shipped set then reads **29 queries over 29 entries at 0.517 / 0.649 /
0.759 / 0.828**, because this session's own write-up joined the store with a
query of its own — and promptly demonstrated the failure mode the phase was
built to catch. Two of them:

- **A long new entry shadows older ones.** `kb-golden-set-lives-in-the-wording`
  now sits in the top five for several questions it does not answer, on
  generic vocabulary. Three queries lost a rank or two to it. That is
  precisely the "a new entry starts shadowing an old one" case the roadmap
  named, observed on the first entry added after the instrument existed.
- **A self-documenting store can contaminate its own fixture.** The write-up
  originally illustrated the paraphrase rule by *quoting a real query*.
  Because the entry lives in the store being searched, it became the top hit
  for that query and displaced the correct answer — recall@5 fell to 0.793
  and came back to 0.828 once the example was invented instead of lifted.
  `test_no_entry_quotes_a_golden_query` now fails the build on any recurrence.
  Worth stating plainly: this hazard exists because the documentation and the
  corpus are the same files, which is a property of this repo, not of golden
  sets in general.

Ablating one signal at a time, with a paired bootstrap over queries (4,000
resamples, 95% CI on ΔMRR):

| variant | success@1 | MRR | ΔMRR vs live | distinguishable |
|---|---|---|---|---|
| live ranker | 0.536 | 0.668 | — | — |
| no IDF | 0.536 | 0.668 | −0.000 | no |
| flat field weights | 0.536 | 0.660 | −0.008 | no |
| no type weights | 0.536 | 0.672 | +0.004 | no |
| no confidence weights | 0.571 | 0.694 | +0.025 | no |
| no episodic recency | 0.536 | 0.674 | +0.006 | no |
| none of the three memory signals | 0.571 | 0.694 | +0.025 | no |
| no length normalisation (b=0) | 0.536 | 0.650 | −0.018 | no |
| boolean term overlap | 0.464 | 0.599 | −0.069 | no |
| **no tf saturation (k1→∞)** | 0.607 | 0.728 | **+0.059** | **yes** |
| **name only, bodies removed** | 0.214 | 0.263 | **−0.406** | **yes** |

Two of eleven ablations are distinguishable. Everything the ranker's design
turns on — IDF, field weighting, and all three memory-specific signals
([[kb-ranked-retrieval]]) — moves the score by about one query, which at n=28
is noise. **This set is a breakage detector, not a tuning instrument.** The
regression test is written accordingly: floors ~4 queries below today's
scores, no tuned constant asserted anywhere, and a `TestTheSetCanStillFail`
case that scores the body-blind ranker and fails if it ever clears those
floors — the day the store outgrows the fixture, the fix is new queries, not a
lower bar.

### The one real finding, deliberately not acted on

Raising `k1` helps because `FIELD_WEIGHTS` weights fields by **repeating their
tokens**, which inflates raw term frequency before BM25 saturates it. That is
the standard motivation for BM25F, but the primary source could not be
retrieved from this session (see Sources), so treat the attribution as
recalled rather than checked — the mechanism below was measured here and does
not depend on it. The principled fix was measured too: proper
BM25F (per-field normalised tf, weighted, saturated once at the end) scores
+0.030 MRR at the standard `k1=1.5`, CI [−0.000, +0.084] — **not
distinguishable** from what shipped, and not distinguishable from just raising
`k1` either.

Nothing was retuned. Picking a constant that wins by one query on a 28-query
set written in the same session that measured it is fitting noise, and the
cost of being wrong is a ranker tuned to its own test. The numbers are
recorded here so a future session with a larger store and a larger set can
re-run the comparison and decide on evidence.

### `kb.py stats`

Counts by type; confidence as written *and* as read today, so decay
([[kb-forgetting-model]]) is visible as a number rather than inferred; link
density with orphan and unlinked counts; median age since verification; median
and total body words; and creation by month as a small bar chart. The same
block is emitted into the site's `data.json`, and the two genuinely new
numbers — links per entry, median days since verified — join the index strip.
No separate stats page: the index already carries six of these tiles and the
status board carries the rest, so a new page would restate the site to itself.

Not on the MCP server. `eval` is a CI instrument and `stats` is a human view;
neither answers a question an agent asks mid-task, which is the bar the
existing six tools meet.

**Honest limits.** One author wrote all 28 queries and all the `also_ok`
judgements, in the session that measured them; a second person would write a
different set and get different absolute numbers. The comparisons above are
paired on the same queries, so they survive that, but the 0.536 does not
transfer. And 28 queries is few enough that every CI here is wide — which is
itself the finding.

27 new tests (380 total): 10 against the real store in
`tests/test_retrieval_golden.py`, 8 for `kb.py eval`, 6 for `kb.py stats`,
3 for the site's stats block.

## Phase 9 — Cross-repo integration · `done` (2026-08-04)

Named as this repo's role in the workspace: keep wikilinks consistent across
`knowledge-base`, the workspace wiki, and `digital-twin`. (The workspace
CLAUDE.md still calls that wiki `knowledge`; no such directory exists — the
live repo is `llm-wiki`, per [[workspace-repo-inventory-drift]].)

- ✅ **Export a portable bundle** — already existed, and was wrong in the one
  place that matters.
- ❌ **Cross-repo dangling-link check in CI** — not built. Empty domain,
  measured; the risk runs the other way and this repo cannot see it.
- ✅ Holds [[twin-sovereignty-constraint]]: one static JSON file over HTTPS,
  or a stdlib stdio server on the same disk. No API key, no vendor LLM, no
  agent in the loop.

**The bundle was already shipped and nobody had noticed.** The phase proposed
exporting "`data.json` plus `memory/`". `data.json` has carried every entry in
full — frontmatter, body, resolved `links`, computed `backlinks`, `status`,
`review_by`, plus `triage`, `stats` and `status_model` — since the site first
shipped (#16, bodies added in #18), is published to Pages on every
memory-touching push, and is 145 KB for 32 entries.
Shipping a second export command would have been the [Phase 6
mistake](#phase-6--ingestion-without-ceremony--done-2026-08-03) again: building
against a flow with no observed instance, when the flow already had a working
implementation under a different name.

**What the bundle got wrong.** It exported `confidence` — the level the author
wrote when they last checked the claim — as the obvious per-entry field, and
the decayed, as-read level only in a *parallel* `status[]` array, keyed by name
and undocumented. So a consumer doing exactly what the phase describes, reading
the bundle without importing the tooling, reads the one number the decay model
exists to correct ([[kb-forgetting-model]]).

Today that is invisible: 0 of 32 entries diverge, and none will before
2026-11-02. On 2026-11-02, **32 of 32** diverge at once — this store was
written in a single nine-day sprint, so `STALE_DAYS` elapses for the whole
corpus in the same week rather than entry by entry. A defect with a zero-sized
blast radius today and a total one on a date you can name is not a latent risk,
it is a scheduled one.

Shipped, all in the builder:

- `entries[]` gains `effective_confidence` and `decayed_by`, from the same
  `kb.effective_confidence` the CLI and MCP paths use. The recorded claim is
  untouched — decay stays a read-time view.
- The bundle gains `stale_days` and `confidence_levels`: **the rule, not just
  its result.** A bundle is read long after `generated`, so a derived field
  has itself aged by the time anyone looks at it. A consumer that has the rule
  can recompute from `last_verified` and never be wrong; one that only has the
  answer is wrong by however long the file has been sitting there.
- `schema_version`, and a contract test pinning the *exact* key set of the
  bundle and of every entry. The existing tests asserted key **presence**
  (`assertIn`), which never fails when a field is dropped or renamed — and the
  field set had already changed in 5 of the 9 commits that ever touched the
  builder: the one that created it, then `body` (#18), `status_model` (#20),
  `stats` (#34), and `authority` (#37), silently every time. Verified the new
  test fails on an added key before keeping it.
- README documents the contract, including which of the two confidence fields
  to trust and why.

**Why no dangling-link checker.** Measured before building, and the domain is
empty. Across the whole store: 66 `[[wikilink]]` occurrences, 27 distinct
targets, **0** pointing outside it. The single unresolved target is the literal
word `wikilinks` used as prose in [[memory-overview-site]], not a link. Nor
could it be otherwise — a link is a bare entry name with no namespace, so a
cross-repo link is not currently expressible. A CI check here would fire zero
times, forever. (Dangling links *within* the store are already a `kb.py lint`
error, confirmed against a planted case, so the builder's silent drop of
unresolvable names is guarded upstream.)

The real exposure runs the other way: another repo citing an entry **here**, by
name or by URL, and this repo renaming or deleting it. That is inbound, and CI
in this repo cannot see it — nor can a routine session, which is scoped to one
repo ([[sibling-repo-access-denied-in-routines]]). What makes an inbound
citation safe is name stability, so the honest deliverable is the promise, not
a checker: entry names are the join key, and the git replay says none has ever
been renamed and no entry has ever been deleted (the only deletions under
`memory/` were generated files and templates in `9dcde20`, matching Phase 4's
replay). That promise is now written down in the README where a consumer will
look, and it is falsifiable — the day an entry is renamed, it is broken.

6 new tests (444 total). Write-up: [[kb-the-bundle-was-already-shipped]].

---

## Phase 11 — The store is one cohort · `done` (2026-08-05)

Not in the original phase list. It was picked up because Phase 9 had left a
loose thread — "0 of 32 entries diverge today, **32 of 32** on 2026-11-02,
because this store was written in a single nine-day sprint" — recorded as a
consequence of one defect when it is really a property of the whole store, and
nothing had gone looking for the rest of what follows from it.

- ✅ **Measure the age structure and replay it forward.** Dated arithmetic, not
  a worry.
- ✅ **Measure what decay is actually worth here.** Nothing, at every offset
  out to two years.
- ❌ **Stagger the review dates** — rejected, `last_verified` is a record.
- ❌ **Prioritise the flat queue** — rejected, two positives in the store's
  entire history cannot support a ranking signal.
- ✅ **Ship the forecast**, in `status`, `stats`, `data.json` and on the
  status board.

**The measurement**, taken across the 32 live entries in the store at the time.
Filing this phase's own write-up makes it 33 across a 9-day window ending
2026-11-03 — the shape is unchanged, and `kb.py status` always reports the live
figure rather than this frozen one. All 32 carry a `last_verified` inside an
**8-day window** — 8.9% of the 90-day `STALE_DAYS` cycle. Eleven of them share
a single date. Replaying the store's own dates forward with nothing else
changing:

| date | what happens |
|---|---|
| 2026-10-04 | `current` empties — all 32 entries `ageing` at once |
| 2026-10-26 | the first entry goes stale; queue 0 → 11 in a day |
| 2026-11-03 | every live entry stale; triage queue 32 items |

The queue holds at most **two distinct severities**, so it sorts by type and
name — 32 rows that all look equally urgent, which reads the same as none of
them being urgent. And the natural repair is the trap: re-verifying the store
in one sweep sets every date to the same day, taking the window from 8 days to
**zero** and scheduling the identical pile-up exactly one cycle later, forever.

**Confidence decay does nothing here, measured rather than argued.**
`effective_confidence` demotes one level per elapsed cycle and `rank()`
multiplies by the decayed level's weight — a design that needs *differential*
age to express anything. With one cohort there is none, so the multiplier is a
near-global constant. The golden set was scored against the real store at +0,
+45, +90, +135, +180, +270, +360, +450, +540 and +720 days, with decay on and
with `effective_confidence` stubbed out entirely:

```
as-of      succ@1    MRR     r@3     r@5     decay disabled
+0          0.517   0.631   0.724   0.793    0.517 0.631 0.724 0.793
+45..+720   0.517   0.634   0.759   0.793    0.517 0.634 0.759 0.793
```

Identical at every offset, and the top-10 order for a confidence-laden query
never changes. The small move between +0 and +45 is episodic recency — a
different signal, and it shows in the decay-off column too. 30 of 32 entries
share one stored level, so decay can only ever reorder the other 2 — and from
**2027-07-30** not even those, because five levels clamp at `unverified` and
the whole store sits there permanently. A store nobody re-verifies ends with
the decay signal switched off, which is the opposite of its purpose. (This
sharpens rather than contradicts Phase 7, which ablated the confidence
multiplier and found it inside the noise band: Phase 7 measured that it does
not help *today*; this measures why it cannot, and until when.)

The claim is narrow on purpose. Decay's **ranking** term is inert here. Its
**display** — `[verified -> high, aged]` in search and context packs — is not,
and is unaffected by the cohort.

**Why the dates were not staggered.** `last_verified` records when somebody
looked. Jittering it would be a lie in the one field the whole freshness model
trusts. The alternative, a per-entry review interval in frontmatter, is the
[Phase 4](#phase-4--temporal-validity--done) mistake exactly: a field whose
domain has to be established before it is added, and nothing here establishes
one. The honest version of staggering needs no field at all — re-verify in
batches on different days, and the dates spread because the checks really did
happen then.

**Why the queue was not prioritised.** To order 32 equally-stale entries you
need a signal for "worth re-checking", and this store cannot supply one. Its
entire history contains **2 entries of 33** whose one-line claim was ever
rewritten — `kb-entry-status-model` and `kb-duplicate-detection-limits`, both
by `kb.py history`'s own reckoning — and both were corrected within days by a
later session's *measurement*, not by the passage of time. Two positives cannot
fit a ranker, and the store is far too young for the staleness clock to have
caught anything yet; the clock's hit rate is not low here, it is unobserved.
Recorded so a future session with a longer history knows what to re-ask.

**What shipped.** `review_forecast()` — every live entry's review date is just
`last_verified + STALE_DAYS`, so the shape of the coming work was always fully
determined and no command reported it. It returns the window, the busiest day,
the count already past review, the count with no usable date, and whether the
shape is a cohort (`span ≤ cycle/3`, with a five-entry floor so a new store's
unavoidable narrowness is not reported as a finding). `kb.py status` ends with
it — a snapshot needs the one line that is about a different day — `kb.py
stats` gains a REVIEW LOAD section, and it goes into `site/data.json` and onto
the status board.

**One defect found on the way out.** Archiving the expired
`holiday-autonomy-mandate` exposed that `kb.py eval` checked whether an
expected entry still *exists*, not whether it is still *retrievable*. Archiving
takes an entry out of the retrieval set and leaves the file, so an archived
expectation passed the check and scored a guaranteed miss on every run
thereafter — the silent fixture rot the check exists to prevent, by the
commoner route. Fixed, and the one golden query that asked about the mandate
retired with it (28 queries, success@1 0.536 / MRR 0.653; floors unchanged, per
Phase 7's standing instruction not to move them).

`data.json` is `schema_version: 2` — `stats` gained a key, and the contract
test now pins the `stats` and `review_forecast` key sets too, closing the same
gap Phase 9 closed one level up.

16 new tests (460 total). Write-up: [[kb-review-load-is-one-cohort]].

---

## Phase 12 — what `last_verified` actually measures — **done** (2026-08-08)

Not on the backlog; picked up as the research-tier item because Phase 11 had
left a loose thread. Phase 11's conclusion was *spread the sweep*. Nobody had
asked the prior question: when this store re-verifies something, what happens?

**It has never happened on its own.** Replaying all 73 commits that have
touched `memory/`, **13 have ever moved a `last_verified` date, and 11 of them
were editing that same entry's body or description in the same commit.** The
two exceptions are both `20a2c4e` on 2026-07-27 — the opening-day commit that
stamped the founding set. In the twelve days since, no standalone
re-verification has ever occurred. `last_verified` is therefore a record of
**authoring activity**, not of review: it moves on entries a session already
had a reason to open, which are the ones whose claims were just re-derived and
are least likely to be wrong. **24 of 35 live entries still carried the date
they were born with.**

**Tested rather than argued** — the store's first standalone sweep, over the
nine oldest of those entries. It came back in three parts:

- **One correct-but-unread entry was actively costing something.**
  [[kb-agent-entrypoint-is-agent-md]] had said since 2026-07-27 that
  `.claude/CLAUDE.md` describes a layout that never shipped, and named all six
  wrong paths right. All six were still wrong twelve days later — in a file
  injected into every session in this repo as an override-everything
  instruction. The entry carried its own remedy ("until that file is rewritten
  or deleted") and [[workspace-improvement-phases]] carried it again as open
  item P1.3. Being right changed nothing for twelve days because nothing
  re-read it.
- **One entry had silently gone incomplete.** A *third* entrypoint (`AGENTS.md`,
  commit `8830ee8`, 2026-08-06) had appeared, describing four memory layers
  rather than seven types and pointing at `/home/jerry/Repos/AGENTS.md` — an
  absolute path on one machine, with an href resolving outside the repo, naming
  a workspace shape already superseded by the `jvanheerikhuize/repos` submodule
  meta-repo. No signal exists for "the world this entry describes gained a
  file."
- **Five of the nine cannot be re-verified from a routine at all.** They rest
  on `~/.claude/settings.json`, the `asdlc` and `digital-twin` repos, the
  claude.ai Routines UI, and a `~/Repos` filesystem in a shape that no longer
  exists. They will arrive in the 2026-10-25 queue with no action a scheduled
  session can take.

That last part revises Phase 11. The coming queue is not one queue: about a
third of it is grounded outside anything an autonomous session can reach, and
spreading does not make those entries checkable. A sweep plan that does not
separate them stalls on the first one it cannot confirm.

**What shipped.** Both files were repaired — `.claude/CLAUDE.md` rewritten
against the real layout, `AGENTS.md` corrected — and each now names
`memory/AGENT.md` as the source it summarises. In `kb.py`:
`review_forecast()` reports `never_reverified` (live entries where
`last_verified == created`) in `status`, `stats` and `data.json`
(`schema_version: 3`); it is computed from dates the store already had, so no
new field. And `kb.py verify --note "<what you checked>"` records the evidence
in `.kb/log.md`, with a stderr warning when it is omitted — the note is not
frontmatter, because an entry records what its author claims, not what a
reviewer did to it, and `kb.py log --action verified` was already the right
home. MCP `propose_update` takes `verify_note` and writes the same record, so
the two write surfaces stay comparable.

**What deliberately did not ship: a "checkable from here" frontmatter flag**,
though five of nine entries want one. It is the Phase 4 shape exactly — a
hand-set field on a judgement that changes when the *session* changes rather
than when the entry does. `sibling-repo-access-denied-in-routines` was true on
2026-07-28 and false by 2026-08-06 while nothing about those entries moved.
Checkability is a property of the reader's access, not of the claim, so it does
not belong on the claim. Reopen condition in the table below.

13 new tests (498 total). Write-up:
[[kb-verification-rides-along-with-authoring]].

---

## Phase 13 — the budget is not a pack size — **done** (2026-08-10)

Not on the backlog; picked up as the research-tier item. Phase 7 measured
whether the *ranker* finds the right entry. Nobody had measured what
`kb.py context` — the command Phase 1 called "the single command an agent
should need", and the literal shape of PURPOSE.md's success metric — actually
hands back.

**It has been shrinking for two weeks.** Replaying all 34 commits that touch
`memory/` with the ranker and the golden set held fixed at today's, so the only
thing varying is the store:

| date | entries | median entry | entries per pack |
|---|---|---|---|
| 2026-07-27 | 10 | 1,324 chars | **5.14** |
| 2026-07-31 | 24 | 2,051 | 3.78 |
| 2026-08-03 | 31 | 2,219 | 3.14 |
| 2026-08-09 | 37 | 2,951 | **2.75** |

Monotone, −47% in thirteen days, budget never touched. Today's pack holds a
median of 3 entries and never more than 4.

**Length is the mechanism; count is not.** Truncating today's 37 entries to the
2026-07-27 median recovers the original figure (**5.25**); cutting the store to
10 entries at today's lengths does not help (**2.39**). The store getting
bigger costs nothing. The store getting *richer* — the Phase 4–12 write-ups run
3,000–6,000 characters each — is what emptied the pack. This phase's own
write-up makes it worse, which is the joke and also the reason a floor shipped.

**Phase 7's instrument cannot see it, by construction.** Sweeping the budget
over the real store:

| budget | entries per pack | recall@pack | recall@3 / recall@5 |
|---|---|---|---|
| 1,000 | 1.57 | 0.571 | 0.714 / 0.786 |
| 2,000 (default) | 2.75 | 0.714 | 0.714 / 0.786 |
| 4,500 | 5.29 | 0.786 | 0.714 / 0.786 |
| 12,000 | 12.86 | 0.857 | 0.714 / 0.786 |

Delivery moves 29 points; every rank metric is bit-identical, because none of
them has a budget term. And `recall@pack` and `recall@3` are **the same 20 of
28 queries** today, not merely the same count — a three-entry pack *is*
recall@3. Phase 7's docstring claim that `recall@5` is "what `kb.py context`
actually delivers" was true on 2026-07-27 and already false when written
(pack: 3.5). Corrected above.

One honest limit: entry length is not an independent axis, since BM25 reads
document length too. The *budget* is the clean axis, and it is the one nothing
measured.

**What shipped.** `recall_at_pack`, `mean_pack_entries` and `budget_bound` in
`eval_report`, printed by `kb.py eval` and scoreable at any budget with
`--budget N`; kept separate from the rank metrics rather than replacing them.
`context_pack` now says **why it stopped** — "3 entries" reads the same whether
three was all there was or all that fit, and those want opposite reactions from
the caller. It names the next entry that did not fit, which is exact and needs
no relevance threshold (it is the one the loop was holding); a count of "further
matches" alone would be noise, since BM25 scores nearly every entry above zero.
**28 of 28** golden queries are budget-bound today. On MCP too. Floors on
`recall_at_pack` and mean pack entries, plus a test that sweeping the budget
moves the pack and leaves the rank metrics untouched — it fails if anyone
removes `recall_at_pack` as redundant.

**What deliberately did not ship: a bigger default budget.** 4,500 tokens
restores the 2026-07-27 figure exactly. Not adopted, because **2,000 was also a
correct number once** — raising it fixes today and starts drifting again with
the next long write-up, just as invisibly. The stable repair is the report plus
the floor, so the next erosion is a failing test. The number is recorded so the
call can be made deliberately; it is Jerry's, not a routine's, because
`DEFAULT_CONTEXT_BUDGET` is caller-facing and every consumer pays for it in
their own context window. Reopen row below.

10 new tests (508 total). Write-up: [[kb-context-budget-is-not-a-pack-size]];
[[kb-ranked-retrieval]] corrected in place.

### Found on the way out: the golden set is one entry from red

Filing this phase's write-up did to the fixture exactly what Phase 7 predicted
a new entry would. `kb-context-budget-is-not-a-pack-size` ranks **#2** for
"what is planned next for this thing", pushing `kb-roadmap` from rank 5 to 6,
and **`recall@5` is now 0.750 against a floor of 0.750** — passing on
`assertGreaterEqual`, with the ~4-query margin the floors were designed to
carry now entirely spent. The next entry anyone files is likely to turn CI red.

The prescribed remedy is Phase 7's own: *the fix is new queries, not a lower
bar.* **The fixture has fallen behind the store** — 28 queries covering 28 of
38 live entries, with these ten uncovered: `kb-archived-is-a-filter-commands-forget`,
`kb-capture-is-a-check-not-an-extractor`, `kb-context-budget-is-not-a-pack-size`,
`kb-instruction-content-lint`, `kb-review-load-is-one-cohort`,
`kb-tests-cannot-cover-an-absent-guard`, `kb-the-bundle-was-already-shipped`,
`kb-timeline-and-heatmap-are-frontmatter-only`,
`kb-verification-rides-along-with-authoring`,
`stranded-branches-track-the-charter-text`.

**But it is not the one-line fix it looks like, and that was measured rather
than assumed.** Ten task-shaped queries were written for those ten entries and
scored: the set goes to 38 queries and **every absolute number falls** —
success@1 0.500 → 0.474, MRR 0.621 → 0.601, recall@3 0.714 → 0.684, recall@5
0.750 → **0.737**, recall@pack 0.714 → 0.658. The additions are harder than the
existing average, so a more representative fixture scores lower, and **the
floors are calibrated to a 28-query instrument that would no longer exist.**
Closing the coverage gap therefore requires re-baselining all five floors in
the same change.

Those ten queries were **not committed.** Re-baselining a floor is precisely
the move Phase 7 warns against, and the session that spent the margin — by
filing the entry that displaced `kb-roadmap` — is the worst-placed one to set
the replacement bars, in the session that measured them, having written both
the queries and the entries they ask about. The numbers above are recorded so a
later session does not have to rediscover the cost; the work is a scoped item,
not a hotfix.

### Closed 2026-08-10 (a later session, no stake in the numbers)

Picked up as the top open backlog item. Wrote ten task-shaped queries for the
same ten uncovered entries, independently of the wording scored and discarded
above — this session never read the discarded queries' text, only the numbers
they produced. First draft missed rank-1 on five of ten; checked each against
`kb.rank` directly before committing anything, reworded the five misses
without borrowing the entry's own vocabulary (same rule the whole set already
runs on — see `test_no_query_restates_its_own_entry_title`), and confirmed all
ten land at rank 1.

Unlike the discarded pass, this one does not depress the set. 38 queries score
**success@1 0.632, MRR 0.721, recall@3 0.789, recall@5 0.816, recall@pack
0.789** — every number *higher* than the pre-add 28-query figures, not lower.
The difference from the discarded attempt is in the ten queries' wording, not
the entries or the ranker; unclear which of the discarded ten scored worse
without their text, which was never written to disk.

All five floors re-baselined in `tests/test_retrieval_golden.py`, ~4 queries
below today's score, the same margin the file has used since 2026-08-02:
success@1 0.40 → 0.50, MRR 0.55 → 0.60, recall@pack 0.55 → 0.65. recall@5 moves
0.75 → **0.70** — lower in absolute terms, but a wider margin than the 0.75
floor it replaces, which today's larger, harder set would have sat on top of
with almost nothing spare. `mean_pack_entries`'s floor is definitional (2.0,
unchanged) rather than score-derived. `TestTheSetCanStillFail` re-verified
against the 38-query set: the name-only ranker scores 0.158 / 0.217, over 45
points of margin under both new floors. 13 tests changed assertions, none
added — the golden set's own size test (`>= 20`) already covers a fixture this
size. Write-up: none — this closes a gap the ROADMAP itself already
diagnosed in the paragraphs above; `.kb/golden.json` and this file are the
record.

---

## No phase is open — what would reopen one

Every phase above is `done`. That is not the same as finished, and the honest
next list is not a set of new ideas: it is the set of **conditions already
recorded inside the closed phases**, each of which was deliberately left
unbuilt because the evidence for it did not exist yet. None should be picked up
before its condition holds.

| Reopens | When | Recorded in |
|---|---|---|
| MCP `2026-07-28` | the reference SDKs and at least one client ship it | Phase 2, "Open" |
| `kb.py import` | a scaffolded copy exists **and** has diverged, giving a real slug collision to write against | Phase 6 |
| BM25F / a `k1` retune | a store and a golden set large enough for +0.030 MRR to be distinguishable from noise; the comparison is already implemented and its numbers recorded | Phase 7 |
| A cross-repo link checker | links gain a namespace, or another repo starts citing entries here — and a session exists that can see both repos | Phase 9 |
| ~~A re-verification prioritiser~~ | **Condition met 2026-08-16 (6 claim rewrites across 41 entries, up from 2 across 33), measured, and the answer is no** — see "Phase 16" below. Nothing available in this repo beats picking the oldest, and the two refined candidates are worse. Reopens only on a *different* kind of evidence: a correction whose cause was visible here, in this tree, on a day before the fix | [[kb-nothing-predicts-the-next-correction]] |
| A second declared-policy registry (episodic-vs-durable, `authority`, confidence decay) | a *fourth* instance of one defect class appears on an axis other than `archived`. The `archived` registry (2026-08-07) was built after three; one instance is a bug, three is a class, and building the registry earlier would have been scaffolding for a problem that had not shown itself | [[kb-tests-cannot-cover-an-absent-guard]] |
| A "checkable from here" split on the review queue | a second session type with *stably* different access exists, so the two populations are a property of the store rather than of who is asking. Today the same entry is checkable or not depending on which sandbox reads it — 2026-08-06's connector grant flipped a whole class overnight | Phase 12 |
| Raising `DEFAULT_CONTEXT_BUDGET` (4,500 restores the original 5.1 entries/pack) | Jerry decides the pack should be bigger. It is a caller-facing default and every consumer pays for it in their own context, so it is not a routine's call — and raising it only re-sets a number that will drift again. **Measured, not changed** | Phase 13 |
| ~~A stranded-branch detector~~ | **Condition met 2026-08-10, built 2026-08-14** — see "Phase 14" below. The row stays for the record of what the condition was | [[stranded-branches-need-a-second-channel]] |
| ~~Archived entries in the ranker's corpus statistics~~ | **Closed 2026-08-18, not deferred** — see "Phase 18" below. The condition this row was waiting on ("more as the archive grows") is measured never to arrive: the effect saturates by the tenth archived entry at ~10% of top hits and a third of a rank position, and has no direction at any size. Its premise was also backwards — archiving is score-neutral under the shipped corpus (0 of 42 orderings move); the *alternative* is what would reweight the store. The corpus is unchanged; what shipped is the declaration it never had | [[kb-a-registry-asks-only-what-it-has-words-for]] |
| Clearing the six-entry floor under the review queue | **Only Jerry can.** All six rest on a sibling repo, the Routines UI, or his own machine, all six were stamped on opening day, and all six therefore come due together on 2026-10-25 — after which `already_due` never falls below 6 and `busiest` never below 6, at any pace a routine keeps. Named in the standing action above. Not an engineering item and not a reason to sweep harder | Phase 15 |

**The stranded-branch detector, measured and deliberately not built
(2026-08-09).** The domain was real — 5 stranded branches in 12 days, one
holding a `lint` fix three days from a red cron. Two candidate predicates were
scored against all 23 sessions:

| predicate | recall | fires today |
|---|---|---|
| open PR on a `claude/*` branch, older than 6h | 1 of 5 | 0 |
| `claude/*` branch with commits not on `main`, tip older than 12h | 5 of 5 | 2 |

The second is the better detector and its threshold is safe by a wide margin:
every one of the 25 legitimately-merged PRs in this repo's history merged within
**62 minutes** of opening (median 4.4), so 12h clears the observed maximum
11-fold. It was not built for two reasons. First, **the diagnosis says the
defect is in the charter's text, not in its observability** — the rate tracks
what `AUTONOMY.md` authorized, 0 of 11 against 3 of 6, and a detector would
report a contradiction it cannot resolve. Fix the contradiction first and
measure whether anything is left to detect. Second, its two standing fires today
are `so8mrh` and `sr8tim`, which only Jerry can clear; shipping a cron that
opens an issue nobody in a routine can close is the `kb-due` close branch
problem in reverse. Build it if the repair fails — the numbers above are the
baseline to beat.

### Phase 14 — the repair failed, so the detector shipped (2026-08-14)

**The condition held for one day.** The charter repair landed 2026-08-09 07:31
(PR #52); `claude/cool-cerf-bb1xow` was stranded 2026-08-10 09:20 and sat
behind open **PR #55 for four days**, against a historical maximum merge
latency of 62 minutes.

**The first objection above is falsified, and by the mechanism rather than the
rate.** Three post-repair sessions with evidence and one stranding settles
nothing statistically. But the stranding was not the failure the repair
addressed: the session did not weigh landing and decline on authorization
grounds — it believed it had landed, and committed
`DEBRIEF.md` text saying "Landed directly on `main` per the git strategy."
Observability is exactly what was missing, because every previous repair is a
message delivered to a session *before* it strands, and the error only exists
*after*. Full argument: [[stranded-branches-need-a-second-channel]].

**The second objection was real and is handled.** `ACKNOWLEDGED` in
`scripts/kb_stranded_issue.py` carries `so8mrh` and `sr8tim` with a required
reason; they render under their own heading with the `push --delete` Jerry
needs, and are excluded from the count that opens the issue. Dry-run against
the live branch list after PR #55 merged: **0 actionable, 2 acknowledged**, so
the cron opens nothing today and its close path is reachable from a routine.
`tests/test_kb_stranded_issue.py` asserts every acknowledged branch is
documented in `AUTONOMY.md`, so the list cannot be grown to silence a real
stranding — the one way this detector could be turned into decoration.

Shipped in the `kb-due.yml` shape Phase 5 established, for the same reason:
`kb_stranded_issue.py` is pure rendering and fully unit tested;
`.github/workflows/kb-stranded.yml` owns the `git for-each-ref` /
`gh pr list` / `gh issue` half that no test here can stand up. Predicate is the
5-of-5 one measured above, unchanged. 21 new tests (530 total).

**Not verified in production.** Nothing in this environment can fire a
scheduled Action, so — as with Phase 5 — the entry is `confidence: high` until
the workflow's first real run. Two things to check when it fires: that a real
stranding opens the issue within a day, and that the close path runs when the
last actionable branch lands. A *false* fire is the signal to lower it.

**First production fire: 2026-08-15T07:05Z, run `31871058533`, success.**
Inventory and render ran; "Open or update issue" and "Close issue" both
skipped; the repo has no open issue. That is 0 actionable / 2 acknowledged,
exactly what the pre-merge dry run predicted, so **the no-false-fire half is
confirmed** — which is the half that would have made the detector decoration.
The two checks above are still unexercised, because nothing was stranded to
exercise them, so the entry stays `confidence: high`. (Scheduling note for
anyone reading run times: the 06:30 cron fired at 07:05, and `kb-due`'s 06:00
cron has landed between 06:42 and 07:48 over its 14 runs. GitHub's scheduled
queue runs 40–110 minutes late here; a missing run before ~08:00 UTC is not yet
evidence of anything.)

**One standing dependency**, worth stating because it is a repo setting and not
code: delete-branch-on-merge must stay on. A squash merge leaves the branch's
commits off `main`, so a squash-merged branch that survived would read as
stranded forever. All 19 PR-merged branches were deleted on the spot, so this
has never happened here.

### Phase 15 — re-verification has one rate (2026-08-15)

Phase 11 said the store is one cohort and the repair is to *spread the sweep*.
Phase 12 asked what a re-verification actually is. Nobody had asked **how many
per day**, and the 2026-08-14 session answered it in prose — "a handful per
calendar day" — after its own 13-entry batch moved the busiest review day from
6 to 15. Simulating that prescription against the store's real `last_verified`
dates says it is wrong by an order of magnitude, and wrong in the same
direction it was correcting.

**There is exactly one sustainable rate: `live entries / cycle`, here 39/90 =
0.433 a day.** Over two cycles, oldest-due first, unreachable entries excluded,
a session declining to re-check anything younger than half a cycle:

| pace | verifications | effective spread | distinct due dates |
|---|---|---|---|
| do nothing | 0 | 4.83d | 12 |
| **0.433/day (cycle rate)** | **66** | **22.04d** | **34** |
| 1/day | 115 | 22.04d | 34 |
| 5/day ("a handful") | 127 | 9.69d | 14 |
| 10/day | 132 | 7.07d | 13 |

Five a day is **nearly twice the work for less than half the spread**. A pace
above the cycle rate empties the pool of entries worth re-checking, then idles
until it refills, and the bursts *are* the clusters. Sampled every 15 days, the
cycle-rate run sits at 4.83 through day +45, reaches 15.36 at +90 and settles at
22.04 by +105: **convergence takes one full cycle and cannot be bought with
effort**, because the span of review dates you create is the span of calendar
days you spend creating them. That makes this a standing habit at a low rate,
not a task a session can finish — which is the opposite of how the backlog has
been treating it.

**The instrument was blind to the thing it warned about.** `review_forecast`
summarised concentration as `busiest`, which names only the tallest bar. On the
real store on 2026-08-15, batching k entries onto today leaves `busiest` at 15
for **every k from 0 to 13** while the effective spread falls 4.83 → 3.46 — so a
session checking whether its batch did harm reads "unchanged" across exactly the
batch sizes it would plausibly do. The 2026-08-14 session's 6 → 15 was luck: its
own pile happened to become the maximum. Shipped `effective_days` (inverse
Simpson index over the due-date histogram, `1 / Σ(nᵢ/N)²`) alongside it, which
is monotone under that batching, plus `sustainable_per_day`; both in `kb.py
status`, `kb.py stats`, the status board and `data.json` (`schema_version: 4`).

**The warning is on `verify`, not in another document.** Three prior repairs
were sentences added to files — the entry in 2026-08-05, its own correction in
2026-08-14, the standing action above — and Phase 14 already measured why that
shape fails: a message delivered before the mistake never reaches a session that
believes it is doing the right thing. `verify_pace_warning()` prints today's
count against the rate once a batch passes it. Deliberately not a refusal and
not a lint failure: a verification that really happened is a true record, and
reverting it would trade it for a false one. The defect is in how many were
scheduled onto one date, so the response is a number, not a veto.

**A floor no routine can lift, found on the way.** The six entries a scheduled
sandbox cannot re-verify were all stamped on opening day and have never moved,
so all six come due on **2026-10-25**, the first day of the queue. After that
date `already_due` never falls below 6 and `busiest` never below 6, at any pace.
This revises Phase 12's conclusion in the other direction: spreading a queue
does not make a third of it checkable, *and* the unreachable part stays a cohort
permanently — so part of the busiest-day number is not a thing to fix, and
reporting it as one invites a session to sweep harder against a wall. Recorded
in the reopen table as Jerry's, not a routine's.

11 new tests (541 total). The archived-axis registry from 2026-08-07 caught
`verify_pace_warning` as an undeclared store scanner before any of them ran,
which is the second time that enumeration has paid for itself. Write-up:
[[kb-reverification-has-one-rate]]; [[kb-review-load-is-one-cohort]] corrected
in place for the second time.

### Phase 16 — nothing predicts the next correction (2026-08-16)

Phase 11's reopen row asked for a **re-verification prioritiser** once the store
had "enough history for *worth re-checking* to be a measurable property — today
it is 2 claim rewrites across 33 entries." Replayed today: **6 claim rewrites
across 41 entries**, plus 30 body edits across 20 entries. The condition holds,
so the row was picked up. The answer is no, and it is no in a way that closes
the row rather than deferring it again.

**The obvious signal is a coarsened age.** The natural predicate — *has a file
this entry cites changed since its `last_verified`* — fires on **31 of 40** live
entries (78%), which is the Phase 4 temporal-validity failure mode. Narrowing it
to the **symbol** level (does a cited `def`/`class`/constant appear in a diff
since then) cuts that to **15 of 40** (38%) and looks like the fix. Scored
against what actually got corrected, it is the worst arm measured.

Every one of the 20 commit-days in this repo's history was replayed; each arm
named a set of entries, and scored a hit when one received a claim or body edit
within 7 days:

| arm | picks | precision | vs. base rate 0.194 |
|---|---|---|---|
| `never_reverified` | 358 | 0.212 | 1.10x |
| age (oldest `last_verified` first) | 382 | 0.199 | 1.03x |
| random | 382 | 0.196 | 1.01x |
| file-level cited-artifact churn | 380 | 0.182 | 0.94x |
| symbol-level cited-artifact churn | 238 | 0.122 | **0.63x** |

Paired bootstrap over days (4,000 resamples, Δ against random): age `+0.002` CI
`[-0.030, +0.034]`, file-churn `-0.015` CI `[-0.037, +0.006]`, symbol-churn
`-0.076` CI `[-0.121, -0.035]`. **The only arm distinguishable from random is
the most refined one, and it is worse.** Churn keyed on `last_verified` is
monotone in age by construction — **318 of 380 file-churn picks (84%) are
entries the age baseline picked anyway** — so refining it does not sharpen a
semantic signal, it discards age information from one.

**The causal reason, from all six claim rewrites.** One rode along in the commit
that caused it (window zero). One was caused by another entry disagreeing, not
by code. Three were caused by state outside this repository entirely — a GitHub
grant and a sibling repo's submodules — with nothing in this tree changing. The
sixth is the decisive one: `kb-agent-entrypoint-is-agent-md` was correct while
`.claude/CLAUDE.md` contradicted it for twelve days, and that file was last
changed `2026-07-25` against the entry's `last_verified: 2026-07-27` — **so the
churn detector was silent for the whole twelve days**, on the case Phase 12
holds up as the store's best catch. Churn detects an artifact *moving*; what
retires a claim here is an artifact being *wrong*, and a wrong file that stays
wrong emits no signal.

**Nothing shipped, deliberately.** The deliverable is the closed row above and
the standing action left alone: oldest due first, one entry, at
[[kb-reverification-has-one-rate]]'s pace, which is within noise of the best arm
measured. Both churn arms would have *looked* like they worked — they fire on
plausible, mostly older entries — so the failure was only visible by scoring
them. Write-up: [[kb-nothing-predicts-the-next-correction]].

---

Three of the eight wait on something outside this repo (a client, a sibling
checkout, a second kind of session), two wait on a decision or an action only
Jerry can take, and the other three wait on the store growing or ageing. Nothing on the
list is blocked on effort, which is why none of it is scheduled — and nothing
left on it can be closed from inside a routine session, which is what the
`kb-due` close branch was until 2026-08-05.

The nearest thing to a standing action is not on that table, because it is not
engineering: **the store's review window is 2026-10-25 → 2026-11-12, and it is
one cohort** (Phase 11). Re-verifying in batches on different days before then
spreads it permanently; one sweep re-creates it. `kb.py status` now says so on
every run, and since Phase 12 it also says how much of that load has never been
re-checked at all (11 of 39 as of 2026-08-15). Three things a session picking up
that standing action should know:

- **The batch size is one, and the pace is `kb.py status`'s `sustainable pace`
  row — 0.433/day here, one entry every 2.3 days.** Not "a handful". Phase 15
  measured it: 5/day does nearly twice the verifications of the cycle rate and
  lands less than half the spread, because a pace above the cycle rate empties
  the ripe pool in bursts and the bursts are the clusters. Convergence takes one
  full cycle at *any* pace, so this is a standing habit, not a task to finish.
- **Which entry: the oldest due, and there is measurably nothing better.**
  Phase 16 scored five ways of choosing against every correction this store has
  ever made; age is within noise of the best arm and the two cited-artifact-churn
  selectors are worse than random. Oldest-first is the answer, not a placeholder
  ([[kb-nothing-predicts-the-next-correction]]).
- **A verify with no `--note` is not a review.** The date will move either way;
  only the note distinguishes "somebody checked this" from "somebody was
  editing this anyway". `kb.py log --action verified` is the trail.
- **Six of the 39 are not a routine's to clear, and they are all due
  2026-10-25** — `asdlc-governed-change-rules`, `purge-context-after-each-change`,
  `routines-ui-not-api-for-prompts`, `twin-sovereignty-constraint`,
  `workspace-audit-2026-07-27`, `workspace-improvement-phases`. They rest on
  sibling repos, the Routines UI, and a machine a scheduled sandbox cannot see.
  Sort them out of the batch first rather than discovering them one at a time —
  and read the floor they leave in the table below before sweeping harder at it.

### Phase 17 — the golden set was fitted to the store it was written against (2026-08-17)

Nothing on the reopen table had met its condition, so the starting point was the
one live number moving on its own: the same 38 golden queries scored
**success@1 0.632 on 2026-08-10 and 0.553 today**, with the ranker untouched.
The floor is 0.50. Three more lost queries breaches it.

**It is not a ranker regression, and it is not ordinary growth either.**
Replaying the fixed query set against the store at all 34 commits that have ever
touched `memory/` — same ranker, same queries, `today` pinned, confidence decay
inert across the whole window — splits the set cleanly in two:

| | filed | s@1 at filing | s@1 today | median rank-1 margin at filing | thin (<20%) at filing |
|---|---|---|---|---|---|
| 28 queries written question-first | 2026-08-02 | 0.536 | **0.500** | 0.359 | 2 of 15 |
| 10 queries added later | 2026-08-10 | **1.000** | **0.700** | 0.128 | 6 of 10 |

Across the **twelve** entries added since it was filed, the question-first
cohort has lost **one** query net, wandering inside a two-query band (13, 14 or
15 of 28) with no trend — the same band it has occupied since 2026-08-02. The
tuned cohort has lost **three of ten across three entries**: 1.000 → 0.900 →
0.800 → 0.700, one per entry filed. A quarter of the set is producing all of
the movement.

**The mechanism is in the 2026-08-10 session's own record**, in `AUTONOMY.md`:
"five of ten missed rank-1 on the first phrasing and were reworded ... until all
ten landed at rank 1." That is selecting the fixture on the outcome the fixture
exists to measure. A cohort filed only when it already scores starts at 1.000 by
construction and has nowhere to go but down — which is exactly the observed
shape, and it is why that session's headline (every number *raised*) was the
opposite of what had happened.

**Two competing explanations were tested and both fail.**

- *These ten targets are simply harder — recent, crowded, similar to each
  other.* A mechanical probe with no query-craft in it (query = the entry's own
  description, the near-ceiling generator from Phase 7) puts **10 of 10** tuned
  targets and **28 of 28** question-first targets at rank 1. The targets are
  equally findable. Low resolution — that probe is near-ceiling for everything —
  so it rules out a gross difficulty gap, not a subtle one.
- *The queries are fitted to the ranker's parameters.* They are not, and this is
  the useful negative. Perturbing the ranker (flat field weights, `k1` 0.6 and
  4.0) costs the tuned cohort 0.100 at worst against the honest cohort's 0.071 —
  one query on ten versus two on twenty-eight, indistinguishable. **The fitting
  is to the store's composition, not to the ranker.** That is why a perturbation
  test cannot detect it and why adding three entries can, and it means the
  obvious guard — "an overfitted set collapses under ablation" — would have
  reported nothing. Deliberately not built.

**The falsifiable test.** Ten fresh queries were written question-first for the
same ten target entries, committed to a file before any ranking was run, and
scored **once** with no rewording: **success@1 0.100**, against the tuned
cohort's 1.000 at filing and 0.700 against today's larger store. Same targets,
same ranker, same day. Anchoring works against this result rather than for it —
the tuned wording had already been read, which pulls a blind attempt toward it.
The gap is selection, not craft or crowding.

**What no existing guard could see.** `test_no_query_restates_its_own_entry_title`
enforces the rule the fixture actually carried — don't borrow the entry's
vocabulary — and the tuned queries pass it comfortably (worst reuse 14%; the
blind cohort's worst is also 14%). Vocabulary overlap is simply not the axis.
Neither is any score: `success@1`, `mrr`, `recall@3`, `recall@5` and
`recall_at_pack` all count a win by 1% of score identically to a win by 80%, so
a fitted set and an honest one read the same until the store grows.

**Shipped: the margin, because it moves before the score does.**
`rank1_margin` per query and `median_rank1_margin` / `thin_at_1` / `rank1_hits`
in `eval_report`, on `kb.py eval`. It is the one number that separated the
cohorts *at filing*, a month before the score did. Reported, never gated — a
threshold here would be a constant fitted to 25 rank-1 hits, which is the Phase 7
mistake. Also shipped: `uncovered_entries`, naming entries no query mentions
(today 3, all filed since 2026-08-14). An uncovered entry competes for every
query and answers none, so it can only lower the score; it is the other half of
any drop and the half that is actually fixable.

**Deliberately not done.**

- **The floors were not re-baselined.** They are ~4 queries under an inflated
  reading, and the honest cohort sits at exactly 0.500 — on the floor. Lowering
  them to buy room would ratify the 0.632 a second time and start a treadmill.
  Instead `_diagnosis()` now names the uncovered entries and the thin-win share
  when a floor breaks, so the coming red reads as "the set is short of queries"
  rather than "retrieval got worse". A red here is now informative.
- **The ten tuned queries were not deleted or reworded.** They are legitimate
  questions; only their filing was selected. Deleting them would lose coverage
  of ten entries and destroy the evidence. They will settle near the honest
  cohort's rate on their own, and the second rule in `.kb/golden.json` stops the
  next set being filed the same way.

**The next action, and why this session did not take it.** Four live entries now
have no golden query — the three filed since 2026-08-14 plus this phase's own
write-up. Writing them is the fixable half of the drop, and **it is not this
session's to write**: the session that measured the bias has a stake in what the
numbers do next, which is the same conflict that produced the bias. It goes to a
later session with no stake, under the two rules now in `.kb/golden.json`,
question first and filed at whatever it scores.

The ten blind queries written as this phase's control are **deliberately not
added to the fixture**. They were written as an experiment's control, their ten
targets already have queries, and a second query per target would double-weight
those ten entries in every metric — an objection that stands independently of
the 0.100 they scored. They live in this section as evidence, not as fixture.

**Found on the way, measured but not changed.** `rank` filters archived entries
out of its results but leaves them in the corpus statistics — `n`, `df` and
`avgdl` are computed over `entry_documents()`, which includes them by declared
policy. So archiving an entry silently reweights every other entry's score: with
today's single archived entry, excluding it moves success@1 0.5526 → 0.5789 and
MRR 0.6755 → 0.6887, a whole query. Whether that is a defect depends on what
`include_archived=True` should mean — under that flag the archived entries
belong in the statistics — so it is a specification question, not a bug to fix
in passing, and fixing it inside the session re-measuring the golden set would
have entangled two independent movements in one set of numbers. Row added to the
reopen table.

---

### Phase 18 — a registry with one slot certified half a decision (2026-08-18)

The backlog was closed and the standing action (one re-verification, only when
behind pace) does not apply: the store has logged **16 verifications in the last
7 days against a sustainable 3.3**, and 29 in 21 days against 9.8 — ahead on
every window, mostly from the 2026-08-14 batch of 14 that
[[kb-reverification-has-one-rate]] exists to discourage. Verifying anything
today would deepen exactly the pile-up the standing action is rationing. So the
item was the one reopen row whose condition is not
waiting on Jerry, a client, or a bigger store: **archived entries in the
ranker's corpus statistics.**

**The row's premise did not survive contact.** It recorded the effect as "worth
one query today (success@1 0.5526 → 0.5789 with the single archived entry
excluded) and more as the archive grows". Both numbers reproduce exactly against
the store as it stood before Phase 17's own write-up entry landed. Against the
store today they are **0.5789 → 0.5789** with no query changing rank at all:
adding one ordinary, unrelated entry erased the entire effect. On the current
42-query set the comparison moves one query from rank 27 to rank 26 and nothing
else.

So the honest measurement is not a snapshot. Holding the **candidate set fixed**
at 20 entries and growing only the corpus — which is exactly "how many archived
entries are in the statistics", with candidate-set size no longer confounded —
over 25 random candidate sets:

| extra documents in the corpus | queries whose top hit changes | mean move of the expected entry |
|---|---|---|
| 0 | 0.0% | 0.000 |
| 2 | 3.0% | 0.102 |
| 6 | 5.4% | 0.186 |
| 10 | 8.2% | 0.252 |
| 16 | 8.4% | 0.270 |
| 22 | 10.0% | 0.296 |

It grows and then it **saturates**: nearly all of the movement arrives by the
tenth archived entry, and the ceiling is a tenth of queries changing their top
hit and a third of a rank position. It never becomes a large effect, and it
never acquires a **direction** — paired over golden queries at three archive
sizes, `success@1` moves **+0.006 (k=5), +0.009 (k=10), −0.003 (k=20)**, the
sign flipping and two of three CIs straddling zero (and those CIs are optimistic
anyway: the same 42 queries recur across trials, so the resamples are not
independent). No further measurement will pick a winner here. That is the
finding, and it is what makes this a specification question rather than a
tuning one — Phase 17 was right about the category and wrong about the size.

**Phase 17's description of the shipped behaviour is also backwards, and this is
the correction that matters.** It wrote that "archiving an entry silently
reweights every other entry's score". Under the shipped corpus it does the
opposite. `entry_documents()` reads every file on disk regardless of the flag,
so archiving does not remove anything from `n`/`df`/`avgdl`: lifting the flag on
the one archived entry and re-parsing from disk moves **70 of 1,780** live
(query, entry) score pairs by **0.001** — the archived date's own tokens
shifting `avgdl`, so not quite perfect neutrality — and reorders **0 of 42**
golden queries, top hit or full ordering. Archiving is a pure
visibility change. The *alternative* is the option that would make archiving a
store-wide score event. The row proposed the reweighting as the cure when it is
the side effect.

Two invariants follow from "the corpus is every file on disk", both measured to
hold today and neither previously tested:

- **Filter-independence.** A live entry's score is identical under `types=`,
  `include_episodic=False` and `include_archived=True` — 42 of 42 golden
  queries, every type. Two searches are therefore comparable, which
  `context_pack` relies on when it fills a budget by comparing scores.
- **Archive-neutrality.** Archiving an entry does not reorder anything for the
  entries that stay (0 of 42 orderings).

**What was actually wrong was the record, not the code.** The store has *two*
BM25 corpora and they disagree: `rank` weighs against `entry_documents()` (43
documents, archived included) while `_bm25_scorer` — behind `dupes`,
`candidates`, `restatements` and the `capture` restatement check — is fed from
`_candidate_docs()` (42, archived excluded, and additionally dropping anything
under `MIN_CANDIDATE_TOKENS`, a second corpus rule with an empty domain today at
0 of 42 skipped). `kb.py search` and `kb.py capture` do not weigh terms the same
way, and nothing said so.

`tests/test_archived_axis.py` is the module built (2026-08-07) to make exactly
this kind of silence impossible, and it **certified `rank` as compliant from the
day it was written**. `rank` declares `EXCLUDES`, which is true of its output;
its corpus `INCLUDES`, which is true of its weights; the registry has one slot
per function, so it recorded the half nobody doubted. That module's opening line
is that you cannot mutate a line that is not there. This is the level above it:
**you cannot declare a decision your vocabulary has no word for**, and a
registry that enumerates functions still only asks the questions it has words
for. Coverage did not miss this and neither did the enumeration — the *schema*
did.

Shipped: a second registry, `CORPUS_POLICY`, on the same pattern. Discovery is
mechanical and independent of the first — a scorer is any function whose body
carries both an `idf` and an `avgdl` name, with no transitive closure, because
a caller passing `docs=` chooses a corpus but does not build the statistics.
Both corpora are declared with their reasons; the misleading halves of the
`rank` and `entry_documents` rows and of `rank`'s own docstring are corrected;
and both invariants above are pinned by tests. Verified by mutation: making the
corpus follow `include_archived` kills both invariant tests, and adding an
undeclared scorer kills the discovery test.

**The corpus itself is deliberately unchanged.** No measurement separates the
two options, the shipped one holds two invariants the alternative breaks, and it
is caller-facing — the same reasoning that left `DEFAULT_CONTEXT_BUDGET` alone
in Phase 13. The reopen row is closed rather than re-armed: it was waiting for
the archive to grow, and growth is now measured to saturate at a bounded,
directionless effect, so that condition can never be met.

### Phase 19 — a constant query has a ceiling (2026-08-19)

Nothing on the reopen table had met its condition, and the standing
re-verification action did not fire (nothing comes due until 2026-10-25). The
item was the one thing every routine session does and nobody had measured:
`AUTONOMY.md` step 1 opened every session with the *same string*,
`kb.py context "autonomous holiday work"`. Phase 13 measured what the pack
hands back; nobody had asked whether the query could reach the right entries.

**The target set is not a fixture.** For each of the 31 commits that modified
an entry which already existed at its parent, the "used" set is exactly those
pre-existing entries — an entry a session went *back* to is an entry it needed.
87 entries across 31 sessions. Each session is replayed against the store as it
stood at its parent commit, with `date.today()` frozen to that session's own
date so confidence decay and episodic recency match what it saw.

| arm | in the pack | |
|---|---|---|
| newest `last_verified` first, no ranker | 8/87 = 0.092 | control |
| the constant query, shipped budget | 17/87 = **0.195** | what sessions got |
| the commit subject as query, shipped budget | 25/87 = 0.287 | |
| constant query, unbounded budget | 40/87 = **0.460** | its ceiling |
| task query, unbounded budget | 84/87 = **0.966** | |

Paired bootstrap over sessions, 4,000 resamples, 95% CI:

- **The ranker earns its keep.** Constant query − no ranker = +0.104,
  CI [+0.025, +0.200]. Even a bad query beats no ranking.
- **At the shipped budget the two queries are not distinguishable** (+0.091,
  CI [−0.024, +0.205]) — both return 2–4 entries, so Phase 13's budget clamp
  hides the difference. Unbounded, it is +0.506, CI [+0.400, +0.604].

**The mechanism is invisibility.** 47 of 87 needed entries score *zero* against
the constant query: they share no term with it, so no budget, no re-ranking and
no tuning returns them. The unbounded arm returns exactly the 40 that were
visible — the ceiling is the visible set. Under a task-shaped query only 2 of 87
are invisible. The brief was also nearly constant (one entry in 30 of 31 packs)
and partly obsolete (16 of 31 led with a mandate archived as spent since
2026-08-05, because "holiday" is the query's most distinctive term).

**Shipped:** `context_pack` reports `retrievable` / `reachable` / `unreachable`
/ `reach`, in the pack text, the JSON, and through MCP. The pack's advice was
actively wrong in this case — it said "Raise `--budget` or narrow the query",
and narrowing only helps entries that matched — so which repair it names is now
decided by comparing the two measured losses, not by a threshold on either.
`AUTONOMY.md` step 1 no longer prescribes a constant.

**Reported, never gated.** Across the 42 golden queries the median reach is
1.000 whether the query hits rank 1 (n=23) or misses (n=19), so reach predicts
nothing among queries that can already see the store. It is a precondition, not
a quality score — which is also why `eval_report` gained no reach term: the
golden set contains only well-formed queries, so the number would be a constant
there and report nothing. 6 new tests (561 total); the `_retrievable`/`rank`
filter agreement is pinned behaviourally and all three filter mutations are
killed. Write-up: [[kb-a-constant-query-has-a-ceiling]].

---

## Done

- Folder-per-type store with schema-validated frontmatter.
- `kb.py` CLI: `list search show new lint triage verify set link edit rm`.
- Staleness and unverified-age auditing, strict mode, weekly cron.
- Published overview site with graph, triage queue, and per-entry pages
  ([[memory-overview-site]]).
- Local editing via `scripts/serve.py` with full CLI parity
  ([[editing-the-kb-without-a-cms]]).
- Mutation log in `.kb/log.md`.
- MCP server over stdio with staged, never-committed writes ([[kb-over-mcp]]).
- Read-time confidence decay and `kb.py archive` — the forgetting half of
  Phase 3 ([[kb-forgetting-model]]).
- `kb.py candidates` / `kb.py judge` and the MCP tools behind them — nearest-
  neighbour blocking plus a durable verdict ledger, the consolidation half of
  Phase 3 ([[kb-duplicate-candidates-by-nearest-neighbour]]).
- `kb.py consolidate` — what a standing verdict still owes: unmerged
  duplicates, overlapping pairs with no edge between them, and passages more
  at home in another entry ([[kb-consolidation-is-owed-work]]).
- `kb.py judge --agreement` and the `contradicted` status — the contradiction
  half of Phase 3, shipped as a second axis on the existing verdict rather than
  as a detector ([[kb-contradiction-is-a-second-axis]]).
- `kb.py history` — what an entry used to say and which revision changed it,
  Phase 4 shipped as provenance rather than as validity intervals
  ([[kb-corrections-happen-in-place]]).
- `kb.py due` (CLI + MCP) and the `kb-due.yml` daily workflow — Phase 5, the
  prospective type now surfaces before a due date lapses, not just after
  ([[kb-prospective-memory-that-fires]]).
- `.kb/golden.json`, `kb.py eval`, and `tests/test_retrieval_golden.py` —
  Phase 7's first half: retrieval scored against task-shaped questions, with
  the fixture's own discriminating power measured and asserted
  ([[kb-golden-set-lives-in-the-wording]]).
- `kb.py stats` — Phase 7's second half: the store in aggregate, also emitted
  into the site's `data.json`.
- `kb.py capture` (CLI + MCP) — Phase 6, shipped as a check rather than as the
  extractor the phase proposed. Measured first: an entry's one-line claim is
  not recoverable even from its own body (1 of 30 entries), so there was
  nothing for a `distill <transcript>` to extract — and a real transcript is
  85% tool traffic with its reasoning persisted encrypted. What capture does
  instead is run the restatement check `AGENT.md` asks an author to do by hand
  ([[kb-capture-is-a-check-not-an-extractor]]).
- Phase 10 — treat memory as untrusted input, and this time "measure before
  building" said build it. Five candidate lint detectors were run against 29
  real entries plus 9 planted prompt-injection-style attacks; unlike Phase 4's
  temporal-validity detector (244 fires, 0 true positives), a union of four
  cheap regex signals caught 7 of 9 attacks with 0 false positives on the real
  store, so `kb.py lint` now flags it (warning; fatal under `--strict`). The
  same pass found the second bullet's risk was already live, not
  hypothetical: three existing entries used identical imperative grammar for
  a non-negotiable constraint and for an admitted "working preference," with
  nothing distinguishing them. Shipped an optional `authority: rule |
  preference` field, surfaced as `[RULE]` / `[preference]` in `kb.py search`
  and `kb.py context` — a context pack is what an agent acts on, so that is
  where the distinction has to show. Third bullet: `kb.py log` (CLI, filters,
  `--json`) and `changes.html` on the site read `.kb/log.md` most-recent-first
  instead of leaving it an append-only file nobody reads bottom-to-top; the
  file itself, and git under it, stay the only record. 21 new tests (401
  total). Write-up: [[kb-instruction-content-lint]].
- Phase 9 — cross-repo integration. (2026-08-04) The portable bundle the
  phase asked for had been published for weeks under a different name:
  `site/data.json` already carries every entry in full. It exported the
  *as-written* confidence as the obvious per-entry field and the decayed,
  as-read level only in a parallel `status[]` array — 0 of 32 entries diverge
  today, 32 of 32 on 2026-11-02, because a store written in one sprint ages
  all at once. Fixed by putting `effective_confidence`/`decayed_by` on each
  entry and shipping `stale_days`/`confidence_levels` so a reader can
  recompute the decay itself, plus `schema_version` and an exact-key-set
  contract test (the old tests asserted presence only, and the shape had
  already changed silently in 5 of 9 builder commits). The dangling-link
  checker was **not** built: 66 wikilink occurrences, 27 targets, 0 pointing
  outside the store, and no syntax that could express one. The real exposure
  is inbound citations, which CI here cannot see, so the deliverable is a
  falsifiable name-stability promise in the README instead of a checker
  ([[kb-the-bundle-was-already-shipped]]).
- Phase 8 — site and graph. (2026-08-03) Execution, not research: all three
  bullets read data `kb.py stats`/`status_report()` already compute. Shipped
  `timeline.html` — growth by creation month as bars, a type × status heat
  map (alpha-blended by count, not CSS `opacity`, so high-decay cells stay
  legible), and every creation/re-verification event newest first — plus
  shareable searches on the index (`?q=`/`?type=` synced via
  `URLSearchParams`/`history.replaceState`, and a copy-link button). Built
  from frontmatter dates only: the Pages checkout is depth-1, so a
  git-derived view would render every entry as never having changed, the same
  constraint that already kept `kb.py history` off the site. 10 new tests
  (438 total). Write-up: [[kb-timeline-and-heatmap-are-frontmatter-only]].
- Phase 11 — the store is one cohort. (2026-08-05) Not in the original list;
  picked up from a loose thread Phase 9 left. All 32 live entries were
  verified inside an 8-day window of the 90-day cycle, so the whole review
  load lands together: `current` empties 2026-10-04, the triage queue goes
  0 → 32 between 2026-10-26 and 2026-11-03 with only two distinct severities
  in it, and re-verifying in one sweep narrows the window to zero and repeats
  the pile-up every cycle. Confidence decay needs differential age and there
  is none — the golden set scores **identically** with decay on and with it
  removed, at every offset out to +720 days, and from 2027-07-30 the five
  levels clamp so it can never reorder anything again. Staggering the dates
  was rejected (`last_verified` is a record, not a knob) and so was
  prioritising the flat queue (2 claim rewrites in 33 entries is not enough
  to fit a ranker). Shipped `review_forecast()` instead — window, busiest
  day, cohort shape — in `kb.py status`, `kb.py stats`, `data.json`
  (`schema_version: 2`) and the status board, plus a fix for `kb.py eval`
  treating an *archived* expectation as resolvable. 16 new tests (460 total).
  Write-up: [[kb-review-load-is-one-cohort]].
- Phase 12 — what `last_verified` actually measures. (2026-08-08) Phase 11 said
  *spread the sweep*; nobody had asked what a re-verification in this store
  actually is. Replaying all 73 commits touching `memory/`: **13 have ever
  moved a `last_verified` date and 11 were editing that entry anyway in the
  same commit**, the other two being the opening-day batch stamp. No standalone
  re-verification had ever happened, and **24 of 35 live entries still carried
  their birth date** — so the field records authoring activity, and the entries
  it skips are precisely the ones nobody has looked at. The first standalone
  sweep (nine oldest entries) found one correct-but-unread entry that had been
  naming a live defect for twelve days (`.claude/CLAUDE.md`, injected into
  every session, all six of its paths still wrong), one entry gone incomplete
  when a third entrypoint appeared (`AGENTS.md`, 2026-08-06), and **five of
  nine that a routine cannot re-verify at all** — which revises Phase 11's
  conclusion, since spreading a queue does not make a third of it checkable.
  Shipped: both files repaired and pointed at `memory/AGENT.md`,
  `never_reverified` in the forecast (`schema_version: 3`), and `kb.py verify
  --note` / MCP `verify_note` recording the evidence in `.kb/log.md`. A
  "checkable from here" frontmatter flag was rejected — checkability belongs to
  the reader's access, not to the claim. 13 new tests (498 total). Write-up:
  [[kb-verification-rides-along-with-authoring]].
- Phase 13 — the budget is not a pack size. (2026-08-10) Phase 7 measured
  whether the ranker finds the entry; nobody had measured what `kb.py context`
  hands back. Replaying all 34 commits touching `memory/` with the ranker and
  golden set held fixed: **the pack has gone from 5.14 entries to 2.75 in
  thirteen days**, monotonically, with the budget never touched. Entry length
  is the whole mechanism — truncating today's 37 entries to the 2026-07-27
  median recovers 5.25, while cutting to 10 entries at today's lengths gives
  2.39 — so the store getting *richer*, not bigger, emptied the pack. Phase 7's
  instrument is structurally blind to it: sweeping the budget 1,000 → 12,000
  moves `recall@pack` 0.571 → 0.857 while every rank metric stays
  bit-identical, because none has a budget term (and `recall@pack` is the same
  20 of 28 queries as `recall@3`, since a three-entry pack *is* recall@3).
  Phase 7's claim that `recall@5` is "what `kb.py context` actually delivers"
  was already false when written. Shipped `recall_at_pack` /
  `mean_pack_entries` / `budget_bound` in `eval_report` plus `eval --budget`,
  and a pack that says whether it stopped on **budget** (naming the next entry
  that did not fit) or on **matches** — 28 of 28 golden queries are
  budget-bound. Raising `DEFAULT_CONTEXT_BUDGET` to 4,500 restores the original
  figure and was **deliberately not done**: 2,000 was also correct once, so
  raising it just re-arms the same silent drift; the repair is the report plus
  a test floor. 10 new tests (508 total). Write-up:
  [[kb-context-budget-is-not-a-pack-size]]; [[kb-ranked-retrieval]] corrected
  in place.

---

## Sources consulted

Only what was actually read, with the date it was read. Claims in this roadmap
that are not backed by a line here are judgement, not citation.

- MCP specification `2025-11-25` — [lifecycle](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/basic/lifecycle.mdx),
  [transports](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/basic/transports.mdx),
  [tools](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/server/tools.mdx),
  [resources](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/server/resources.mdx),
  and [schema.json](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/schema/2025-11-25/schema.json)
  (2026-07-28) — protocol version string, stdio framing rules, tool/resource
  message shapes, `ToolAnnotations` fields.
- [The 2026-07-28 MCP Specification Release Candidate](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/)
  (2026-07-28) — the stateless core, removal of the initialize handshake, and
  the explicit "no automatic compatibility with 2025-11-25" statement that
  Phase 2's version decision rests on.
- [CoALA](https://arxiv.org/abs/2309.02427) — the memory taxonomy the folder
  layout follows.

- Near-duplicate detection background (2026-07-28) — [Broder, *Identifying and
  Filtering Near-Duplicate Documents*](https://cs.brown.edu/courses/cs253/papers/nearduplicate.pdf),
  [Stanford IR, *Near-duplicates and shingling*](https://nlp.stanford.edu/IR-book/html/htmledition/near-duplicates-and-shingling-1.html).
  Source of the shingling construction, the standard threshold bands
  (0.7–0.8 conservative, 0.5–0.6 aggressive), and the warning that shingle
  estimates degrade on very short documents — which is why `dupes` skips
  entries under 20 shingles and says which ones it skipped.

- Blocking / entity resolution (2026-07-29) — the "cheap recall-oriented blocker
  feeding an expensive pairwise matcher" split, and the recall-vs-comparisons
  trade-off it turns on, are standard record-linkage vocabulary, not an
  invention here. The reference work is Papadakis et al., *Blocking and
  Filtering Techniques for Entity Resolution: A Survey*, ACM Computing Surveys
  53(2), 2020 ([arXiv:1905.06167](https://arxiv.org/abs/1905.06167)).
  **Read at summary level only** — both the arXiv and the authors' PDF mirror
  returned 403 from this session, so the full text was not retrieved. It is
  cited for the terminology. The numbers in Phase 3 are this store's own
  measurement and rest on nothing in it.

- Field-weighted BM25 / BM25F (2026-08-02) — **not retrieved.** Both
  [Robertson & Zaragoza, *The Probabilistic Relevance Framework: BM25 and
  Beyond*](https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf)
  and the Wikipedia summary returned 403 from this session, as arXiv did on
  2026-07-29 — outbound fetches are broadly blocked here, not flaky. Phase 7's
  BM25F reasoning is therefore recalled, not checked. What *is* checked is the
  measurement: the BM25F variant was implemented and scored against the golden
  set, and its numbers stand on that run alone.

**Near-neighbour projects — re-checked 2026-07-28.** The Phase 2 sentence
originally named four; two are confirmed, two are dropped as uncited.

- [Basic Memory](https://basicmemory.com/) — confirmed. Markdown files plus a
  SQLite index and a knowledge graph, served over MCP. Its
  [skills repo](https://github.com/basicmachines-co/basic-memory-skills) ships a
  "memory-defrag" skill that merges duplicates and removes stale information —
  direct prior art for Phase 3 — but publishes no similarity metric and does not
  say whether merges are automatic or proposed, so it settles nothing about the
  hard part.
- **brain.md** — confirmed. Local-first markdown vault with an MCP server, and
  notably a `context_for_query` token-budgeted chunk-packing tool that is the
  same idea as this repo's `kb.py context`, arrived at independently.
- **kb-mcp, "Agent Memory"** — could not be confirmed as distinct projects.
  Dropped rather than left as plausible-looking filler.
