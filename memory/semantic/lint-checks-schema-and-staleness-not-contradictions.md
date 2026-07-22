---
name: lint-checks-schema-and-staleness-not-contradictions
type: semantic
description: kb.py lint validates structure (schema, dupes, dangling links, staleness, overdue prospective) — it does not detect contradictions between entries' content
confidence: verified
source: Phase 6b doc correction and Phase 11b CI step rename, docs/roadmap.md
created: 2026-07-23
last_verified: 2026-07-23
links: [schema-enforcement-gap-found-via-dotfiles-dogfooding]
---

`python3 scripts/kb.py lint` checks, and only checks:

- frontmatter conforms to `memory/schema/entry.schema.json` (required
  fields present, `name` is kebab-case, `type` is one of the 7 enum values)
- no duplicate `name` slugs across the repo
- no dangling `links:` (a link target that doesn't exist as an entry)
- staleness: entries whose `last_verified` is old, or whose `confidence`
  is still `unverified`, are flagged (fatal only under `--strict`)
- orphaned entries (nothing links to them) are flagged as warnings
- `prospective` entries past their `due` date are flagged

It does **not** read entry bodies for meaning and cannot detect that two
entries assert contradictory facts. Earlier docs, `AGENT.md`, and the CLI
`--help` text overstated this at points during development — implying or
outright claiming lint did some form of consistency/contradiction
checking. That was corrected in Phase 6b (doc/schema overstatement pass),
and the CI workflow step was renamed in Phase 11b to describe what it
actually runs (lint + staleness check) rather than what it was once
implied to do.

Practical implication: a clean `kb.py lint` run means the KB is
structurally sound, not that its content is internally consistent.
Catching contradictions is still a human (or agent-review) job.
