---
name: kb-is-file-based
type: semantic
description: the knowledge base requires no infrastructure — plain markdown files only
confidence: verified
source: docs/plan.md design decision
created: 2026-07-22
last_verified: 2026-07-22
links: [distill-session-into-memory]
---

This knowledge base stores every memory type as a markdown file with YAML
frontmatter under `memory/<type>/`. There is no database and no vector
store — search is keyword-based over frontmatter and body text via
`scripts/kb.py search`. This trades away semantic/embedding search in
exchange for zero infrastructure and full human readability/editability,
per the project's explicit requirements (see `docs/plan.md`).
