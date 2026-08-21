---
name: kb-the-bundle-was-already-shipped
type: semantic
description: ROADMAP Phase 9's portable export already existed as site/data.json — the real defect was that it published the as-written confidence, which diverges from the store's own reading for 0 of 32 entries today and 32 of 32 on 2026-11-02
confidence: verified
source: scripts/build_site.py collect()/build(); tests/test_build_site.py BundleContractTests; measured against the 32-entry store on 2026-08-04
created: 2026-08-04
last_verified: 2026-08-14
links: [kb-forgetting-model, memory-overview-site, kb-corrections-happen-in-place, sibling-repo-access-denied-in-routines, kb-capture-is-a-check-not-an-extractor, kb-roadmap, kb-a-hung-deploy-reports-as-cancelled]
---

ROADMAP Phase 9 asked for "a portable bundle (`data.json` plus `memory/`) that
another repo can read without importing this tooling" and a cross-repo
dangling-link check. Measured first, both bullets turned out to be about
something other than what they said.

## The export already existed

`site/data.json` has carried every entry in full — frontmatter, `body`,
resolved `links`, computed `backlinks`, `status`, `review_by`, plus `triage`,
`stats`, and `status_model` — since the site first shipped, and it is
published to Pages on every memory-touching push. 145 KB for 32 entries, no
service and no key behind it. (**The last clause is a claim about a workflow,
not about the file a consumer actually fetches** — between 2026-08-09 and
2026-08-21 no deploy completed at all, so the published bundle was twelve days
stale while every push looked normal. A consumer should trust the bundle's own
`generated` field over any promise about how often it is refreshed; see
[[kb-a-hung-deploy-reports-as-cancelled]].) Writing an `export` command would have repeated
the [[kb-capture-is-a-check-not-an-extractor]] mistake: building against a flow
whose implementation already exists under a different name.

The same is true of the on-disk path. Every script resolves `ROOT` from
`__file__`, not the working directory, so a sibling checkout can already mount
`scripts/mcp_server.py --read-only` by absolute path from any cwd and get
*ranked* retrieval rather than raw entries. Verified by running it from `/tmp`.
That is the answer for anything on the same disk; `data.json` is the answer for
everything else.

## What was actually wrong: the bundle published the uncorrected number

Each entry exported `confidence` — the level its author wrote **when they last
checked the claim** — as the obvious per-entry field. The decayed, as-read
level lived only in a *parallel* `status[]` array, keyed by name and documented
nowhere. So a consumer doing exactly what the phase describes reads the one
number [[kb-forgetting-model]] exists to correct.

The size of that is worth stating precisely, because it is not a gradient:

| date | entries whose exported `confidence` differs from the store's own reading |
|---|---|
| 2026-08-04 (today) | 0 of 32 |
| +30d, +60d | 0 of 32 |
| **2026-11-02** (+90d) | **32 of 32** |

`STALE_DAYS` is 90 and this store was written in a single nine-day sprint, so
the whole corpus crosses the threshold in the same week rather than entry by
entry. A defect invisible today and total on a date you can name is a scheduled
one, not a latent one.

**Export the rule, not only its result.** A bundle is read long after
`generated`, so any derived field in it has itself aged by the time anyone
looks. Shipping `stale_days` and `confidence_levels` alongside
`effective_confidence`/`decayed_by` lets a reader recompute from
`last_verified` and be right at read time; a reader given only the answer is
wrong by however long the file has been sitting there. This generalises past
confidence: any value a bundle derives from a date should travel with the rule
that derived it.

**A published shape is a contract.** The bundle gained `schema_version` and a
test pinning the *exact* key set of the bundle and of every entry. The tests
that existed asserted key **presence** (`assertIn`), which cannot fail when a
field is dropped or renamed, and the field set had already changed in 5 of the
9 commits that ever touched the builder — `body`, `status_model`, `stats`,
`authority` — silently every time.

## The link checker has an empty domain, and the risk runs the other way

Across the whole store: 66 `[[wikilink]]` occurrences, 27 distinct targets,
**0** pointing outside it. The single unresolved target is the literal word
`wikilinks` used as prose in [[memory-overview-site]]. Nor could it be
otherwise — a link is a bare entry name with no namespace, so a cross-repo link
is not expressible today. A check in this repo's CI would fire zero times,
forever. (Dangling links *inside* the store are already a `kb.py lint` error,
confirmed against a planted case, so the builder dropping unresolvable names
from `links` is guarded upstream.)

The exposure is **inbound**: another repo citing an entry here by name or URL,
and this repo renaming or deleting it. CI here cannot see that, and neither can
a routine session ([[sibling-repo-access-denied-in-routines]]). What makes an
inbound citation safe is name stability, so the deliverable is the promise
rather than a checker — entry names are the join key, and the git replay says
none has ever been renamed and no entry has ever been deleted, matching the
replay in [[kb-corrections-happen-in-place]]. The promise is written in the
README where a consumer looks, and it is falsifiable: the day an entry is
renamed, it is broken.
