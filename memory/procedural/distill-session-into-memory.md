---
name: distill-session-into-memory
type: procedural
description: how an agent should turn a finished session into persisted memory
confidence: verified
source: memory/working/distill.template.md
created: 2026-07-22
last_verified: 2026-08-03
links: [kb-is-file-based, kb-capture-is-a-check-not-an-extractor]
---

1. Before ending a session, run through `memory/working/distill.template.md`.
2. **Write the claim yourself, in a sentence or two.** Nothing extracts it for
   you: the claim an entry makes is not present in the material the session
   produced, measured — see [[kb-capture-is-a-check-not-an-extractor]]. The
   deciding is the work; the tooling checks the result.
3. Run `scripts/kb.py capture --type <type> --name <name>` with the claim on
   stdin, in a file, or in `--text`. It reports which existing entries the
   claim reads like *before* writing anything, then files it as
   `confidence: unverified` with the top neighbour linked.
   - `--check` gives you the neighbours and writes nothing.
   - If it reports that the claim points decisively at an existing entry, that
     entry is almost certainly where it belongs: `--extend <name>` appends it
     there instead of adding a near-twin.
4. Read the entry back and set `confidence` honestly using the rubric in
   `memory/AGENT.md`. Facts checked directly against a filesystem, command
   output, or primary doc are `verified`; anything taken on a single
   unconfirmed report is at most `high`. A captured entry stays `unverified`
   until you do this.
5. Add whichever of the other neighbours belong in `links:`. `capture`
   prefills only the top one — an edge the author would have drawn about 70%
   of the time — and prints the rest rather than guessing them.
6. Run `scripts/kb.py lint` to catch dangling links or missing fields.
7. Run `scripts/kb.py triage` to see whether the pass left anything orphaned,
   unlinked, or unverified.
