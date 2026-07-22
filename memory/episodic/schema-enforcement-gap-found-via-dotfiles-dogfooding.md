---
name: schema-enforcement-gap-found-via-dotfiles-dogfooding
type: episodic
description: kb.py lint never read entry.schema.json — surfaced only by real usage in the scaffolded dotfiles copy, not by design review or synthetic tests
confidence: verified
source: Phase 6 (p6c) and Phase 9 (p9a/p9b) of docs/roadmap.md
created: 2026-07-23
last_verified: 2026-07-23
links: [lint-checks-schema-and-staleness-not-contradictions, self-knowledge-vs-scaffolded-consumer-knowledge]
---

During Phase 1, `memory/schema/entry.schema.json` was written as the formal
frontmatter contract (required fields, kebab-case `name`, the 7-type enum).
`kb.py lint` was built alongside it but, in practice, never loaded the
schema file — it only checked the narrower set of things its own code
happened to test for (duplicate slugs, dangling links). Nothing failed in
this repo's own CI, because this repo's own entries always satisfied the
narrower checks too.

The gap stayed invisible until Phase 9: `scaffold.sh` was run against a real
project (dotfiles), two genuine entries were authored there
(`kb-is-file-based`, `distill-session-into-memory`), and `kb.py lint`
reported "clean" — correctly, by its actual behavior, but misleadingly
relative to what the docs and `--help` text claimed lint did. The schema
file was sitting there, referenced by nothing.

What surfaced it wasn't a design review or the unit test suite added later
in Phase 8 — it was a second real repo exercising the tool with real
content. Fixed in Phase 6 (p6c, done concurrently with this discovery being
written up) by loading the schema in `cmd_lint` and enforcing its
`required` fields, the `name` pattern, and the `type` enum.

Takeaway: a scaffolded consumer repo passing lint is not the same claim as
"the tool checks what its docs say it checks" — dogfooding against a real
external repo is what closed that gap, not code review of this repo alone.
