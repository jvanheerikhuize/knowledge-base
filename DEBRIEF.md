# DEBRIEF — autonomous holiday work (2026-07-28 → 2026-08-05)

Jerry: this is everything shipped while you were away. **Triage by marking only
what you don't want** — tick a box (`[x]`) to flag an item for revert/discussion;
everything left unticked stands as-is. Each line links the commit or PR.

## How this ran

Daily cloud routine "Autonomy — daily workspace session" (Sonnet 5, 11:00
GMT+2) on `jvanheerikhuize/knowledge-base`, governed by [AUTONOMY.md](AUTONOMY.md).
Set up 2026-07-27 before you left.

## Shipped (mark only what you DON'T want)

- [ ] 2026-07-27 Autonomy charter + this debrief scaffold added (setup, this PR)
- [ ] 2026-07-28 **The KB is now an MCP server** — `scripts/mcp_server.py`, stdio, stdlib-only. Six tools (`context`, `search`, `get`, `triage`, `status`, `propose_update`) plus entries as `kb://entry/<name>` resources; `.mcp.json` registers it so any client in this repo picks it up with no setup. Writes are staged in the working tree and **never committed** — you review with `git diff`. `--read-only` drops the write tool entirely. 39 new tests (166 total, green). ROADMAP Phase 2 done.
- [ ] 2026-07-28 Implemented MCP **2025-11-25**, not the `2026-07-28` revision published the same day — it deletes the initialize handshake, has no automatic compatibility, and no client speaks it yet. Rationale and the migration path are in ROADMAP Phase 2; revisit when the SDKs ship.
- [ ] 2026-07-28 `scaffold.sh` now also copies `mcp_server.py`, so a KB scaffolded into another repo is agent-callable, not only a CLI.
- [ ] 2026-07-28 ROADMAP gained a **Sources consulted** section with real URLs and read-dates, and an explicit note that the near-neighbour projects cited in Phase 2 are *not* yet re-verified — flagged rather than papered over.
- [ ] 2026-07-28 Two KB entries: `kb-over-mcp` (the design and its constraints) and `sibling-repo-access-denied-in-routines` (see below).

- [ ] 2026-07-28 **The KB now forgets** (ROADMAP Phase 3, forgetting half). Confidence decays one level per 90 days at read time, so a `verified` fact untouched for a year competes as `unverified` — computed on read, reversed by `kb.py verify`, and *never* written back, so your recorded claim survives. Both numbers show wherever they differ (`[verified -> unverified, aged]` in search, `confidence: unverified (recorded as verified, aged)` in context packs).
- [ ] 2026-07-28 **`kb.py archive <name>`** retires an entry from retrieval without deleting it — out of search, context packs, and triage; still readable, still linked, still in the graph, with its own `archived` status on the board and the site. `--undo` reverses it; `rm` still exists for entries that should genuinely go. Also reachable over MCP through `propose_update`. 28 new tests (194 total, green).

- [ ] 2026-07-28 **`kb.py dupes`** — finds text recorded twice (an entry added twice, a scaffolded copy drifting back, an agent re-recording its own work). Reports Jaccard *and* containment, since containment catches the case Jaccard scores lowest: a short entry wholly absorbed into a longer one. Also flags entries still holding the unfilled template, which is deliberate.
- [ ] 2026-07-28 **The finding behind it, which matters more than the tool.** I measured whether lexical similarity can find *paraphrases* before trusting it: a hand-written restatement of an existing entry ranked **#14 of 210 pairs** (token Jaccard) and **#16** (tf-idf cosine) — below thirteen pairs of entries that merely share a subject; on raw shingles it scored 0.000. So shingling ranks topical neighbours above real restatements, and the roadmap item as originally written was not buildable. `dupes` is scoped honestly to near-copies, prints its own limit, and a regression test pins the paraphrase as *not* flagged so nobody "fixes" it by lowering the threshold. Write-up: `kb-duplicate-detection-limits`. 22 new tests (208 total, green).
- [ ] 2026-07-28 Re-checked the near-neighbour projects the ROADMAP had been citing from memory: **Basic Memory** and **brain.md** confirmed (brain.md independently arrived at token-budgeted context packing, same idea as `kb.py context`; Basic Memory ships a "memory-defrag" skill but publishes no similarity metric); **kb-mcp** and **"Agent Memory"** could not be confirmed and are dropped rather than left as plausible-looking filler.

- [ ] 2026-07-29 **Semantic duplicate detection works after all — yesterday's negative result was too broad.** Yesterday I measured that no lexical score can *decide* whether two entries restate each other, and concluded lexical similarity was the wrong signal. The measurement was right; the conclusion wasn't. A **global threshold** asks "is this pair similar in absolute terms", and absolute similarity is dominated by how much vocabulary a *topic* shares — which varies far more between topics than duplication does within one. Asking each entry "which entries are you *most* like" cancels that out. Re-measured against **seven** hand-written paraphrases planted in the store: globally the worst sat at **#81 of 378 pairs**; as each entry's single nearest neighbour, unioned both ways, **all seven** were caught in **19 pairs — 5% of the space**.
- [ ] 2026-07-29 **`kb.py candidates` + `kb.py judge`** (ROADMAP Phase 3, consolidation half). `candidates` narrows the pair space and then *refuses to rule* — about one candidate in three to eight is real and no score says which, so an agent reads both entries and decides, the same division of labour `kb.py new` already uses. No embedding model, no vendor call, nothing to keep running. `judge` records `duplicate`/`overlap`/`distinct` in `.kb/verdicts.json`, bound to a digest of both entries' claim text: re-verifying or relinking doesn't expire a verdict, rewriting a body does. Both are on the MCP server too (`duplicate_candidates` read, `judge` staged-write). 23 new tests (231 total, green).
- [ ] 2026-07-29 **Ran the first full pass: 42 pairs judged, no duplicates** (24 overlap, 18 distinct) — and the incremental design then proved itself, adding the write-up entry cost 6 more judgements rather than another 42. One real find: `kb-agent-entrypoint-is-agent-md` and `workspace-repo-inventory-drift` describe the same stale `.claude/CLAUDE.md` and weren't linked — now they are. Closest near-miss, recorded for a future `consolidate`: `persist-insight-to-knowledge-base` steps 3–5 restate most of `distill-session-into-memory`.
- [ ] 2026-07-29 `kb-duplicate-detection-limits` **corrected in place** rather than left standing — its measurement and its regression test are still valid and still passing, but its conclusion now points at the new entry, `kb-duplicate-candidates-by-nearest-neighbour`. The ROADMAP carries the lesson: a negative result can be real, reproducible, correctly tested, and still wrong, when what was measured is one *framing* of the question rather than the question.

- [ ] 2026-07-30 **The KB checks for contradictions now — and the checker is not a checker.** ROADMAP Phase 3's last open item asked for a mechanical detector: same subject, conflicting frontmatter, a body that negates one it links to. I measured that before building it. Nine contradictions planted in a copy of the store — eight hand-written, one **real, recovered from git** (the pre-correction `kb-duplicate-detection-limits` against the entry that overturned it) — and every cheap signal scored against them: global topical similarity puts the positives anywhere from **#2 to #107 of 435**; claim-level sentence alignment catches **4 of 9**; negation polarity catches **5 of 9** and is structurally blind to the commonest shape of all, two competing *positive* assertions ("20 repos" against "22 repos", no negation anywhere). Its false positives are negation-scope errors — "this is **not** just a preference" is agreement.
- [ ] 2026-07-30 **What shipped instead: a second axis, not a second command.** The nearest-neighbour blocker built for duplicates on 2026-07-29 already caught **8 of 9** at its default and **9 of 9** at `-n 5`. Nothing was missing but a way to *say it*: `duplicate|overlap|distinct` answers how much two entries say the same thing and has no value meaning "these disagree", so a pair could be judged, look settled, and never have been asked. `kb.py judge` gained `--agreement agree|contradict` (a pair can restate *and* disagree), standing contradictions became the `contradiction` triage reason and the `contradicted` status — above `broken`, because every other status means nobody checked and this one means somebody checked and the store is wrong. Deliberately **not** a lint failure: lint checks form. Same axis on the MCP `judge` tool. 36 new tests (267 total, green).
- [ ] 2026-07-30 **Absence is stored as absence, so the ledger could not lie about its own coverage.** Omitting `--agreement` writes no key at all, which meant all **46** verdicts recorded before the axis existed came back into `candidates` marked "never checked for contradiction" rather than quietly passing as fine. That re-opening also exposed a real sharp edge and I fixed it: re-judging a pair used to blank the previous pass's note. It does now only if you ask (`--note ""`).
- [ ] 2026-07-30 **First full pass — 75 pairs at `-n 5`, and it found a real one.** `kb-entry-status-model` said every entry sits in one of **eight** statuses and its table omitted `archived`; `kb-forgetting-model` said archiving gives an entry its own `archived` state on the board. Both could not be true. It had stood for two days — since `archive` shipped — through a full duplicate-judging pass, a clean lint, and a clean triage, because nothing had ever asked the question. Reconciled in place (that entry now carries the ten-status table); store clean on both axes. Worth the ratio: the same 45 pairs read for duplicates the day before returned **zero** duplicates, and the second question returned a defect.
- [ ] 2026-07-30 One KB entry, `kb-contradiction-is-a-second-axis`, plus the stale-quote cleanup it forced — `memory/AGENT.md`'s standing "no such checker exists yet" admission, and `kb-roadmap`'s promise that the sentence would change when Phase 3 shipped, both now say what is actually true.

- [ ] 2026-07-31 **`kb.py consolidate` shipped, and the queue the roadmap named was the empty one.** The item was scoped as "propose merges", working from pairs standing at `duplicate`. Measured against the store's own ledger: **87 verdicts across two full passes, zero duplicates** (44 `overlap`, 43 `distinct`). A store curated by an agent that judges pairs as it writes them does not accumulate duplicates — it accumulates overlap, so a merge-only `consolidate` would have been dead code on day one.
- [ ] 2026-07-31 **The real defect was seven overlapping pairs with no link between them, and nothing could see it.** `judge` prints "link them if they are not linked yet" once, when the verdict is passed — then the pair settles, drops out of `candidates` forever, and the advice is never checked again. Seven of the 44 overlapping pairs had no edge. `lint` is structurally blind to this: it catches links that point *nowhere* and entries *nobody* links to, both properties of a single entry, while a missing edge between two well-connected entries is a property of a **pair** and only the ledger knows the pair is real. All seven read, all seven genuine, all seven drawn.
- [ ] 2026-07-31 **The sub-entry half — "this paragraph restates another entry" — needed a different metric, measured before building.** Seven hand-written restatements planted in a copy of the store, 2728 (passage, entry) pairs: passage shingle-containment caught **1 of 7**; scoring the passage as a BM25 **query** caught **7 of 7** in 4.5% of the space. Containment fails one level down for the reason it failed at entry scale — shingles measure shared *phrasing*, which a restatement is precisely what does not share. Two filters then cut 124 candidates to **28 (1%) with recall still 7 of 7**: the passage must beat **its own host scored with the passage removed** (a paragraph more at home elsewhere than where it is written — removal is load-bearing, leave it in and the host wins trivially every time) and clear a 1.5× margin over the runner-up.
- [ ] 2026-07-31 **The default margin's cost, recorded rather than hidden.** 1.5 holds the planted set at full recall but drops the one real case this store already knew about — `persist-insight-to-knowledge-base` steps 3–5 restating `distill-session-into-memory`. Those steps *are* found (they beat their own host) but the runner-up sits close, because procedure steps share vocabulary with half the store where distinctive prose does not. `--margin 1.0` surfaces them, at 63 passages to read instead of 22. The planted positives were topical prose and the default is tuned to them; when hunting a restated *procedure*, lower the margin.
- [ ] 2026-07-31 **First full pass: 7 edges drawn, 22 restatement proposals read, 2 real.** `kb-roadmap` was retelling the entire contradiction-detection finding that `kb-contradiction-is-a-second-axis` exists to hold — cut to what it uniquely knows plus the link. And the `persist`/`distill` case: the restated steps went, and the one thing they added (the verified-vs-`high` rubric) moved into `distill`'s step 3, where the procedure lives. The other 20 are an entry legitimately discussing its neighbour, which is what a blocker is supposed to produce. Rewriting those three entries expired **26 verdicts** and reopened them — the design working, not a cost to route around — all re-judged, plus one genuinely new pair. Store clean on both axes, no missing edges, lint and triage clean.
- [ ] 2026-07-31 38 new tests (**305 total, green**), `consolidate` on the MCP server as a read tool, ROADMAP Phase 3 closed as `done`, and one KB entry: `kb-consolidation-is-owed-work`.
- [ ] 2026-07-29 **Test consolidation & audit** (AUTONOMY.md backlog item, done). Read all 231 tests against the four scripts they cover. Trimmed a handful of redundant assertions/tests (numbers re-checked that a more specific test already pinned, one strict-subset test, one confidence-decay test whose age landed on the same clamp branch as another — repurposed into a new intermediate-step test instead of dropped). Two fixed bugs the gap analysis found, each confirmed by reverting the fix and watching the new regression test fail: `kb.py set <name> links <value>` wrote a bare string instead of list syntax, silently corrupting the entry (`cmd_link` then treats the string's characters as the link list); `kb.py dupes` had no archived-entry filter where `kb.py candidates` did, so an archived entry could be flagged as a live duplicate of a current one. Also added coverage for previously-untested error paths: MCP `propose_update`/`judge` on a missing entry, malformed JSON-RPC (non-object `params`, missing `method`, `resources/read` without `uri`), `build_site`'s empty-KB rendering (mermaid and index-page placeholders), and `serve.py` malformed POST bodies / a route missing its required name. 231 → 244 tests, `kb.py lint` clean, all green. Write-up: `kb-test-audit-2026-07-29`.
- [ ] 2026-07-30 **Test consolidation & audit, and it found a real bug.** Read all four suites (2304 lines, 267 tests) against their source. Overlap was minimal — CLI-vs-MCP layering is deliberate, not duplication — so nothing was cut. The gap sweep found `cmd_rm`'s referrer-scan loop (`for t, other in iter_entries()`) shadowing the outer `t` that had already been resolved to the *deleted* entry's own type: the ingest-log line written after the loop recorded whichever type `iter_entries()` last yielded, not the entry actually removed. Invisible in every prior test because they only ever built single-type stores. Fixed (`_other_type` instead of `t`), with a regression test I verified fails against the unfixed code before confirming it passes against the fix. Also closed two coverage gaps the same read turned up: `kb.py context --limit` and `iter_entries()`'s skip of `README.md`/`*.template.md` inside a type folder were both previously unexercised. 4 new tests (271 total, green), lint clean. [`ea3d76f`](https://github.com/jvanheerikhuize/knowledge-base/commit/ea3d76f)

- [ ] 2026-07-31 **KB hygiene pass and site polish (AUTONOMY.md backlog,
  both done) — audited, both already clean.** `kb.py triage` clean, `kb.py
  status` shows all 26 entries `current` (none stale/isolated/overdue), so
  there was nothing to re-verify or connect. Rebuilt the site locally and
  checked all 31 generated pages programmatically: zero broken internal
  links, no unresolved `[[wikilink]]` markup leaking into rendered bodies,
  dark-mode CSS and a responsive viewport present, `data.json`'s entry count
  matches the index. Could not fetch the live Pages URL from this session —
  this environment's network policy blocks `jvanheerikhuize.github.io`
  (403 at the proxy, not a fluke) — so checked the deploy pipeline instead:
  the latest `pages.yml` run succeeded and nothing touching `memory/**` or
  `.kb/**` has landed since, so the published site already matches the
  store. No content changed, no code changed; both items closed as clean
  audits rather than left unchecked for a future session to redo.

- [ ] 2026-08-01 **ROADMAP Phase 4 shipped, and both frontmatter fields it asked for turned out to have nothing to describe.** Phase 4 wanted `valid_until` ("this was true until March") and `supersedes: <name>`. I replayed every commit that has ever touched `memory/` and classified every change — 38 creations, 30 bookkeeping-only revisions, 22 rewrites, 6 appends, 3 deletions (all three of generated files or a moved template, **never an entry**). **0 of 26** entries have a claim with a knowable expiry date; all 22 rewrites were facts overtaken by an event nobody could have dated. **0 of 22** rewrites retired a whole entry — including the one case `supersedes` was written for, `kb-duplicate-detection-limits`, which was deliberately corrected in place because its measurement and regression test were still valid and only its conclusion moved.
- [ ] 2026-08-01 **The mechanism behind those zeros is the actual finding.** Obsolescence here is repaired *by the change that causes it, in the same commit*: `1d1c713` deletes `scripts/visualize.py` **and** rewrites all four entries citing it; `9dcde20` deletes `docs/plan.md`, moves the generated tree, **and** fixes both entries naming the old paths. The agent that changes the code owns the memory about the code and changes both at once, so a claim is never stale-and-unrepaired for an interval that a validity interval could describe. Worth knowing that this is a property of an agent-maintained store, not a law — a store whose facts describe something outside the repo would not behave this way.
- [ ] 2026-08-01 **I tested the stronger framing before concluding, and it failed harder than the weak one.** Rather than dates, bind validity to a *source*: 92% of entries cite a repo path, so flag the entry when the path stops resolving. Replayed across all 21 commits that touched `memory/`, that check fired **244 times with 0 true positives** — and never fired on the real breaks above, because of the same-commit repair. All 16 of its standing fires today are *correct* citations: five entries cite sibling repos this one cannot see, `site/data.json` is a build output under a gitignored path, and `kb-agent-entrypoint-is-agent-md` names `ci/lint.py` and `ci/regenerate_graph.py` inside a table **whose whole subject is that they do not exist**. An entry about a missing file necessarily cites a missing file. Coarsening to "cited file changed since `last_verified`" is no better — 38 of 82 references fire, because almost everything cites `scripts/kb.py`.
- [ ] 2026-08-01 **What shipped: `kb.py history <name>`** — what an entry used to say and which revision changed it. Correction-in-place means the superseded wording exists only in git, where no part of the tooling could reach it. Each revision is labelled by what it changed — claim / body / bookkeeping — because `verify` and `link` touch an entry far more often than an author does and an unlabelled `git log` buries the rewrites under the date-stamps; where the one-line claim changed, the superseded wording is quoted. Also on the MCP server as a read tool. **The number is small and I have not dressed it up:** 2 of 26 entries have had a claim rewritten, 8 more have body edits. What justifies it is that the need was already felt twice with no tool to meet it — one session corrected `kb-duplicate-detection-limits` in place and added a link because there was no way to *show* the change, and the contradiction pass the next day recovered a prior version of that same entry from git **by hand** to use as test data.
- [ ] 2026-08-01 **Deliberately not on the published site**, and the reason is a trap worth keeping: `actions/checkout` defaults to `fetch-depth: 1`, so a site build would render every entry as having exactly one revision and never having changed — a confident lie, worse than absent. `history` reports `shallow: true` and says its history is truncated instead. Putting revisions on the site means changing the Pages workflow first, which belongs with Phase 8's timeline view.
- [ ] 2026-08-01 13 new tests (**334 total, green**), lint and triage clean, one KB entry (`kb-corrections-happen-in-place`), and a full judging pass over the 26 pairs the new entry and the roadmap edit opened — 3 missing edges found and drawn, store clean on both axes. One bug caught by its own test while writing it: an initialized-but-empty git repo makes `git log` exit non-zero, which I was reporting as "not a git repository"; no git, no repository, and an uncommitted entry are now three different messages.

- [ ] 2026-08-01 **One drive-by fix, found while re-checking the site build** (scope expansion, recorded per the charter). `build_site.py` rendered code spans first and then ran the wikilink and emphasis passes over the result, so markup *inside* a code span was still processed — an entry documenting the `` `[[wikilinks]]` `` syntax rendered as a dangling link to an entry called "wikilinks". That was the only broken-looking link on the published site and it was a false one; the 07-31 polish pass missed it because it checked `href` targets, and this one renders as a `<span>`, not an `<a>`. Code spans are now held aside and restored last. 3 tests, 2 confirmed failing against the unfixed renderer.

- [ ] 2026-08-01 **ROADMAP Phase 5 shipped — prospective memory now surfaces before it lapses, not just after.** `kb.py due [--within Nd]`, CLI and MCP, lists prospective entries whose `due:` date has arrived or is approaching, soonest first — built the same way `triage_report`/`status_report` are (one function, three surfaces agree by construction). An already-overdue entry always shows regardless of `--within`, since it is definitionally due; unparseable dates are left to `triage`'s existing `invalid-due` check rather than duplicated here.
- [ ] 2026-08-01 **`.github/workflows/kb-due.yml`**, a daily cron, opens, updates, or closes one running tracking issue ("Knowledge base: entries coming due") via `gh issue create/edit/close` — one checklist issue, not one per entry, since the store holds three prospective entries today and a per-entry issue would be more process than the problem. The formatting is split out into `scripts/kb_due_issue.py` (`due.json` → title + body) specifically so the testable half is unit tested (5 tests) and the untestable half — the actual `gh` calls, since nothing in this environment can fire a scheduled Action — stays a thin, readable shell script rather than logic worth testing badly. **Not yet verified against a real firing** — flagged as the entry's open question, re-check after it runs once.
- [ ] 2026-08-01 18 new tests total (**353 total, green**): 8 for `due_report`/`cmd_due`, 3 for the MCP `due` tool (plus the existing tool-listing test extended), 5 for `kb_due_issue`. Lint and triage clean. One KB entry, `kb-prospective-memory-that-fires` (`confidence: high`, not `verified`, for the reason above), linked into the graph; four nearest-neighbour candidates it raised were read and judged `distinct`/`agree` — topically adjacent (other `kb.py` commands, the published site) but about different things. ROADMAP Phase 5 closed.

## Blockers / notes

- **2026-07-31 — two routines are running, neither in the afternoon, and one of
  them has been losing its work since 07-29.** Jerry asked why no afternoon
  session had run. Reconstructed from commit times (all times GMT+2):

  | routine | fires | model | state |
  |---|---|---|---|
  | undocumented | ~09:15 | Opus (research) | ✅ merged every day — 07-28 … 07-31 |
  | "Autonomy — daily workspace session" | ~11:15 (cron `0 9` UTC) | Sonnet (execution) | ⚠️ **work stranded on branches, never merged, never debriefed** |
  | afternoon | — | — | ❌ **no session has ever run after 11:18** |

  **Nothing fires in the afternoon on any day**, so Jerry's observation is
  correct. I cannot see or change routine configuration from inside a routine
  session — there is no RemoteTrigger tool here and no claude.ai credential, the
  same sandboxing as `sibling-repo-access-denied-in-routines`. So this half is
  Jerry's to fix in the UI; the steps are below.

  **The more urgent finding is the second row.** The 11:00 routine ran on
  2026-07-29 and 2026-07-30, did real work, pushed it, and stopped:

  - `claude/cool-cerf-so8mrh` (07-29) — the **Test consolidation & audit**
    backlog item: audit suite for overlap and gaps, **plus two bug fixes in
    `scripts/kb.py`**, and an episodic entry recording the audit.
  - `claude/cool-cerf-sr8tim` (07-30) — **a `cmd_rm` bug fix** (its referrer
    scan overwrote the deleted entry's type), a semantic entry on artificial
    uniformity in test corpora, and its own edits to `AUTONOMY.md` and
    `DEBRIEF.md`.

  That last detail is the one that matters: **that session did write its debrief
  line — it just never reached `main`.** So the single document Jerry triages
  has been silently missing two days of work, including three bug fixes, and the
  backlog still shows "Test consolidation & audit" unchecked, which is why this
  session nearly picked it up a third time.

  **Recovered 2026-07-31 on Jerry's instruction — both branches rebased and
  merged.** All three bug fixes are on `main`, each re-verified by reverting the
  fix and watching its regression test fail. 305 → 321 tests, lint and triage
  clean. Two things the merge exposed that are worth keeping:

  - **The two sessions did the same backlog item twice.** 07-29 did "Test
    consolidation & audit" and 07-30 did it again, because the first pass never
    reached `main` so the box still read unchecked. They found *different* bugs,
    so the duplicated effort was not wasted — but it was still duplicated, and
    the backlog now records both passes under one item.
  - **They also wrote the same test twice.** Both added a `non_object_params`
    MCP test at the same spot. The 07-30 version is kept: it additionally
    asserts the server still answers after the bad request, which is what "not
    a crash" actually means.

  Recovery was verified line by line, not assumed: every test method and every
  source line the two branches added is on `main`, with exactly one deliberate
  omission — `test_non_object_params_is_an_invalid_params_error`, the weaker
  half of the duplicate above.

  **One thing left for you: delete the two branches.** They are still on the
  remote. A routine session cannot remove one — the git relay rejects
  `git push --delete` with `the remote end hung up unexpectedly`, and the
  GitHub MCP tools have no delete-branch call. That matters more than tidiness
  now, because `AUTONOMY.md` tells future sessions to treat an unmerged
  `claude/*` branch as possibly-unfinished work; both are named there as
  already-recovered so nobody re-merges them, but the note goes away when the
  branches do.

  **Why "push to a branch" was not enough.** `AUTONOMY.md` offers three git
  routes and only the PR route ends in `main`. A session that reads "logical
  pieces of work → push directly to a work branch" follows the charter exactly
  and still leaves nothing merged, nothing reviewed, and nothing in the debrief.
  The charter should say that a session ends with its work on `main` or with the
  reason it is not; that is fixed below.

  **What Jerry needs to do (UI only — claude.ai/code/routines):**
  1. If an afternoon routine was ever created via the API, check whether it is
     **disabled**. Per `routines-ui-not-api-for-prompts`, a trigger written with
     a repo slug as `environment_id` accepts the write, then fails its first run
     with `environment_not_found` and **auto-disables itself** — silently, which
     looks exactly like "it never ran". Re-enabling without fixing the
     environment just re-disables it; set the repo through the UI picker.
  2. Otherwise create it in the UI, not the API: instructions (a short pointer at
     `AUTONOMY.md`), repository, model, and connectors are all UI-only fields.
  3. Note the timezone trap: the API stores `cron_expression` in **UTC** while
     the UI shows **local**. The existing 11:00 routine is cron `0 9` UTC. An
     afternoon slot of 15:00 local is `0 13` UTC.

- **2026-07-28 — the session started read-only; you fixed it mid-run.** For most
  of this session `git push` returned 403 from the git relay and the GitHub API
  returned `403 Resource not accessible by integration`; reads worked
  throughout, so the credential was read-only rather than absent. You
  reconnected GitHub partway through and the push went straight out — the work
  above is on `claude/wizardly-dijkstra-idh56e`, nothing was lost. Worth
  remembering because the failure mode is quiet: a routine can do a full
  session of work, pass every test, and only discover at the end that it cannot
  push. Note for the record that the Claude GitHub App install is *not* what
  controls this — per the web docs, App installation drives PR webhooks and
  Auto-fix, while session git access comes from how the GitHub account is
  connected (web onboarding or `/web-setup`).

- **2026-07-28 — routine sessions cannot reach sibling repos.** Probed
  directly: cloning `jvanheerikhuize/digital-twin` fails on auth, and the
  GitHub MCP tools refuse any repo other than `knowledge-base`. This is how the
  routine is scoped, not something a session can raise. **Consequence:** the
  workspace-docs-drift item (`~/Repos/CLAUDE.md` lists 20 repos, disk has 22)
  cannot be done from here, and neither can any other cross-repo work — it is
  now marked blocked in `AUTONOMY.md` rather than left to be re-attempted every
  session. **If you want autonomous work happening in other repos, configure
  one routine per repo** the same way this one was set up.
