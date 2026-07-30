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

## Blockers / notes

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
