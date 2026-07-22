---
name: distill-session-into-memory
type: procedural
description: how an agent should turn a finished session into persisted memory
confidence: high
source: memory/working/distill.template.md
created: 2026-07-22
last_verified: 2026-07-22
links: [kb-is-file-based]
---

1. Before ending a session, run through `memory/working/distill.template.md`.
2. For each item worth keeping, run `scripts/kb.py new --type <type> "<name>"`.
3. Fill in the body and set `confidence` honestly using the rubric in
   `memory/AGENT.md`.
4. Link related entries via the `links:` frontmatter field.
5. Run `scripts/kb.py lint` to catch dangling links or missing fields.
6. Run `scripts/visualize.py` to refresh `memory/_generated/graph.mmd`.
