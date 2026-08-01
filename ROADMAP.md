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

## Phase 5 — Prospective memory that fires · `planned`

**Gap.** `prospective/` entries carry `due:` dates that only surface if someone
runs `triage`. The one memory type that is about the future is inert.

- Scheduled workflow (the weekly `strict-lint` cron is already there) opens or
  updates a GitHub issue when an entry comes due.
- `kb.py due [--within 14d]` for the same view locally.

## Phase 6 — Ingestion without ceremony · `someday`

**Gap.** `memory/working/distill.template.md` is filled in by hand, so capture
depends on remembering to capture.

- **`kb.py distill <transcript>`** — extract candidate atomic facts from a
  session log into a staging area as `confidence: unverified` drafts, for
  review before they join the store. Atomic extraction plus an explicit review
  gate is what keeps a store from filling with restated context.
- **`kb.py import`** — pull entries from a scaffolded copy in another repo,
  which is the missing half of the existing "keeping a scaffolded copy in sync"
  flow.

## Phase 7 — Measure whether the memory is any good · `someday`

**Gap.** There are 98 tests of the tooling and none of the memory. Nothing
tells you whether retrieval got better or worse as the store grew.

- **Retrieval golden set** — a small fixture of query → expected-entry pairs,
  asserted as a regression test. Catches the day a new entry starts shadowing
  an old one.
- **`kb.py stats`** — counts by type and confidence, link density, orphan rate,
  median entry age, growth over time. Surfaced as a panel on the site.

## Phase 8 — Site and graph · `someday`

- Timeline view over `created` / `last_verified`.
- Staleness and confidence heat map, so decay is visible at a glance.
- Saved searches as shareable URLs.

## Phase 9 — Cross-repo integration · `someday`

Named as this repo's role in the workspace: keep wikilinks consistent across
`knowledge-base`, the workspace wiki, and `digital-twin`. (The workspace
CLAUDE.md still calls that wiki `knowledge`; no such directory exists — the
live repo is `llm-wiki`, per [[workspace-repo-inventory-drift]].)

- Export a portable bundle (`data.json` plus `memory/`) that another repo can
  read without importing this tooling.
- Cross-repo dangling-link check in CI.
- Must hold [[twin-sovereignty-constraint]]: no API key, no vendor LLM, no
  agent required in the loop for any of it to work.

## Phase 10 — Treat memory as untrusted input · `someday`

A knowledge base that feeds agents is an injection surface. A memory entry that
influences tool selection is a privileged execution path, and model robustness
does not cover it.

- Lint check for instruction-shaped content in entry bodies.
- Keep system-rule memory and preference memory distinguishable, so a
  preference cannot be read as a rule.
- `.kb/log.md` already records every mutation; surface it as a reviewable
  "what changed" view rather than an append-only file nobody reads.

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
