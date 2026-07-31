# Agent Memory — Entry Point

Read this file first. It is the single point of entry into this knowledge
base, regardless of which agent or framework is operating on it.

## What this is

A file-based, human-readable/editable memory store organized around the 7
types of agent memory (CoALA-derived taxonomy). No database, no vector
store — just markdown files with YAML frontmatter, plus scripts in
`../scripts/` to search, audit, triage, and edit them.

## Folder-per-memory-type

| Folder | Memory type | Use it for |
|---|---|---|
| `semantic/` | Semantic | Durable facts, preferences, domain knowledge — true regardless of when learned |
| `episodic/` | Episodic | Records of specific past events/task runs — what happened, what worked, what failed |
| `procedural/` | Procedural | Skills, workflows, how-to playbooks — reusable steps, not one-off facts |
| `working/` | Working | NOT persisted content. Holds only the template used to distill a session into episodic/semantic entries before context is lost |
| `retrieval/` | Retrieval / external | Indexed reference material meant to be keyword-searched (`kb.py search`), the file-based stand-in for a vector store |
| `parametric/` | Parametric | Documentation-only. Records the boundary of what's assumed already known by any capable model, so entries aren't wasted restating it |
| `prospective/` | Prospective | Future intentions, scheduled goals, things to do or check later |

## Adding a memory

1. Classify the information into one of the 7 types above.
2. Run `scripts/kb.py new --type <type> "<name>"` to scaffold an entry from
   the template (see `../.kb/templates/entry.template.md`).
3. Fill in the body. Set `confidence` honestly (see rubric below).
4. Link related entries via the `links:` frontmatter field.

## Confidence-scoring rubric

| Value | Meaning |
|---|---|
| `verified` | Cross-checked against a primary source or repeated observation |
| `high` | Single reliable source, internally consistent, not yet cross-checked |
| `medium` | Plausible, single weak/indirect source |
| `low` | Speculative or inferred, not directly sourced |
| `unverified` | Just captured, not yet assessed |

**Confidence ages.** The level above says how well a fact was checked when it
was checked. Retrieval demotes it one level per 90 days since `last_verified`,
so a `verified` fact nobody has revisited in a year competes as `unverified`.
The file is never rewritten — `kb.py verify <name>` is what resets the clock.
When you see `medium (recorded as verified, aged)` in a context pack, that is
this: trust the first number, and treat the gap as a prompt to re-check.

**Before you add an entry, check you are not restating one.** `kb.py dupes`
catches text recorded twice, but it will *not* catch you making the same claim
in different words — that was measured, and lexical similarity ranks topical
neighbours above real restatements (see the `kb-duplicate-detection-limits`
entry). So the check that matters is the one you do: `kb.py search` the claim
first, read what comes back, and extend an existing entry rather than adding a
near-twin.

After the fact, `kb.py candidates` will put your new entry's nearest neighbours
in front of you — but only as pairs to *read*, never as a verdict. Judging them
is your job, and it is **two questions, not one**:

```
kb.py judge <a> <b> duplicate|overlap|distinct --agreement agree|contradict
```

The verdict says how much the two overlap. `--agreement` says whether they can
both be true — an independent axis, because a pair can restate *and* disagree.
Leaving `--agreement` off does not clear a pair; it records that nobody looked,
and the pair stays in the queue. This is the store's only contradiction check:
it was measured that no cheap signal separates "these two disagree" from "these
two are about the same thing", so an agent reading the pair is the detector
(see the `kb-contradiction-is-a-second-axis` entry).

Both answers survive re-verifying and relinking; rewriting either body reopens
the pair. A pair judged `contradict` stays in the queue, and both its entries
sit at `contradicted` in `triage` and `status`, until somebody reconciles
them.

**A verdict is not the end of it.** `kb.py consolidate` reports what standing
verdicts still owe — a `duplicate` nobody merged, an `overlap` with no link
between the two entries, and passages that score higher against a different
entry than against their own. That last one is how a paragraph restating
another entry is found; `dupes` cannot see it, because shingles measure shared
phrasing and a restatement shares none. Lint cannot see the missing links
either: it checks one entry at a time, and a missing edge is a property of a
pair. Everything `consolidate` prints is a proposal — most restated passages
are an entry legitimately discussing its neighbour, so read before cutting,
and use `--margin 1.0` when hunting for a restated *procedure* (see the
`kb-consolidation-is-owed-work` entry for why the default misses those).

Re-run `scripts/kb.py lint` periodically (or via CI, see
`.github/workflows/kb-lint.yml`) — it flags entries whose `last_verified`
is stale, `confidence: unverified` entries older than 30 days, dangling
`links:`, duplicate slugs, and violations of `../.kb/schema/entry.schema.json`
(missing required fields, malformed `name`, invalid `type`). It still does not
detect content-level contradictions between entries, and it never will: lint
checks form, and whether two claims can both be true is not form. That question
is asked of candidate pairs instead — see below — and reported as the
`contradicted` status rather than as a lint failure.

## Entry status

Confidence says how much an entry is trusted; `last_verified` says how
recently anybody looked. Status collapses both — plus links and due dates —
into one answer per entry: *what is the single next thing to do about it.*
Every entry sits in exactly one status, and if several apply the worst wins.

Run `scripts/kb.py status` for the board, `--legend` for this table, or open
`status.html` on the site.

| Status | What it means | How to change it |
|---|---|---|
| `contradicted` | Another entry has been judged to disagree with it — one of the two is wrong | reconcile them, then `kb.py judge <a> <b> <verdict> --agreement agree` |
| `broken` | A frontmatter date will not parse, so the entry escapes every freshness check | `kb.py set <name> last_verified YYYY-MM-DD` |
| `overdue` | A prospective entry whose `due` date has passed — a reminder that already fired | act on it, then `kb.py set <name> due YYYY-MM-DD` (or `kb.py rm <name>`) |
| `stale` | Not re-checked in over 90 days; may still be true, nobody has looked | re-check against the source, then `kb.py verify <name>` |
| `unverified` | Recorded but never confirmed against a primary source — a claim, not a fact | confirm it, then `kb.py verify <name> --confidence verified` |
| `provisional` | Confidence is `low` or `medium` — believed, but the evidence was indirect | check it directly, then `kb.py verify <name> --confidence verified` |
| `isolated` | Nothing links to it, or it links to nothing; unreachable by following the graph | `kb.py link <other-entry> <name>` |
| `ageing` | Still fresh, but past two-thirds of the way to the staleness cutoff | nothing now; re-verify before the review date |
| `current` | Verified recently, trusted, and connected. Nothing to do | nothing; re-verify by the review date to stay here |
| `archived` | Retired from retrieval on purpose; still readable and still in the graph | nothing; `kb.py archive <name> --undo` puts it back |

`review_by` is `last_verified` + 90 days — the date an entry falls to `stale`
if left alone. This is what keeps "clean" from quietly meaning "unexamined":
`triage` lists only what is already wrong, `status` accounts for everything.

## Retrieving what you need

Start a task with `scripts/kb.py context "<what you are about to do>"`. It
returns a paste-ready brief: the highest-ranked entries, trimmed to a token
budget (`--budget`, default 2000), each carrying its own provenance —
confidence, `last_verified`, and the file it came from — so nothing enters
your context unattributed. Episodic logs are left out by default because they
describe one past run and crowd out durable knowledge; pass `--episodic` to
include them.

`scripts/kb.py search` is the same ranking without the packaging: BM25 over
the whole store, best first, with a score column and `--limit`. Ranking is
type-aware — a term in an entry's *name* counts for more than one buried in
the body; procedures and facts outrank scratch files; recency is applied to
`episodic` entries only (a log decays, a fact does not); and confidence is a
small nudge that reorders near-ties without ever outranking a real match.

## Interacting with the knowledge base

```
scripts/kb.py list [--type TYPE]         # list entries, optionally filtered
scripts/kb.py search "<query>" [--limit N] [--type T]   # ranked search, best first
scripts/kb.py context "<task>" [--budget N]             # paste-ready context pack for a task
scripts/kb.py show <name>                # print one entry
scripts/kb.py new --type TYPE "<name>"   # scaffold a new entry
scripts/kb.py lint                       # schema, duplicate-slug, dangling-link, and staleness checks

scripts/kb.py status [--type T] [--status S] [--legend]   # where every entry stands, and what moves it
scripts/kb.py triage                     # what needs attention, most urgent first
scripts/kb.py verify <name> [--confidence LEVEL]   # stamp last_verified as today
scripts/kb.py archive <name> [--undo]    # retire from retrieval; the file and its links stay
scripts/kb.py dupes [--threshold 0.5]    # pairs whose text overlaps near-verbatim
scripts/kb.py candidates [-n 3] [--all]  # pairs that may restate each other — read them, then judge
scripts/kb.py judge <a> <b> duplicate|overlap|distinct --agreement agree|contradict [--note "..."]   # record both calls
scripts/kb.py consolidate [--margin 1.5]  # what those verdicts still owe: merges, missing links, restated passages
scripts/kb.py set <name> <field> <value> # edit one frontmatter field
scripts/kb.py link <name> <target> [--remove]      # manage links: safely
scripts/kb.py edit <name>                # open the file in $EDITOR
scripts/kb.py rm <name> [--force]        # delete, refusing while still linked
```

Mutations are appended to `../.kb/log.md`, so the history of the store is
readable without reading git.

## Using this store as MCP tools

If your client speaks MCP, prefer it over the CLI — no shelling out, no parsing
printed text. `../.mcp.json` registers the server, or run it directly:

```
python3 scripts/mcp_server.py [--read-only]
```

| Tool | Use it for |
|---|---|
| `context` | the first call of a task — a budgeted brief with provenance |
| `search` | ranked hits without the packaging |
| `get` | one entry in full |
| `triage` | what is wrong or ageing, worst first |
| `status` | where every entry stands and what moves it |
| `duplicate_candidates` | pairs to read for restatement *and* for disagreement |
| `consolidate` | what judged pairs still owe — merges, missing links, restated passages |
| `judge` | record both answers about a pair — staged, never committed |
| `propose_update` | stage an edit — **it does not commit** |

Entries are also resources (`kb://entry/<name>`, plus `kb://agent` for this
file), so a client can attach one without a tool call.

**What `propose_update` does and does not do.** It writes to the working tree
and stops. Nothing you change through it is committed, published, or visible to
anyone else until a human reads `git diff` and commits. Say so when you use it:
report the change as *proposed*, not as done.

## Browsing the knowledge base

The whole store is published as a browsable site — index, per-entry pages,
and a link graph colored by memory type:

https://jvanheerikhuize.github.io/knowledge-base/

Build it locally with `scripts/build_site.py`, or run `scripts/serve.py` to
browse and edit it in a browser. Nothing generated is committed.

## Further reading

- `../README.md` — design rationale, architecture diagrams, and layout of the repo
