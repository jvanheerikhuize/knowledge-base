---
name: self-knowledge-vs-scaffolded-consumer-knowledge
type: semantic
description: this repo's own memory/ should record the KB's own design/build history; a scaffolded copy's memory/ should record that consumer repo's own operational knowledge — same schema, different subject
confidence: verified
source: dogfooding exercise, 2026-07-23 — populating this repo's own memory/ for the first time
created: 2026-07-23
last_verified: 2026-07-23
links: [schema-enforcement-gap-found-via-dotfiles-dogfooding, kb-is-file-based]
---

`scaffold.sh` copies the exact same folders, schema, and CLI into a target
repo (see the README's "Scaffolding into another repo" section). That
makes the two situations structurally identical — but they are not the
same situation semantically:

- **This repo's own `memory/`** (knowledge-base) is the KB *dogfooding
  itself*: entries here should be about the KB's own design decisions,
  bugs found and fixed, and build history — e.g. "lint didn't enforce the
  schema until Phase 6c" (`schema-enforcement-gap-found-via-dotfiles-dogfooding`)
  or "the KB is file-based by design" (`kb-is-file-based`). This is a
  knowledge base *about the tool*, maintained *by* the tool.

- **A scaffolded consumer repo's `memory/`** (e.g. dotfiles' copy) should
  hold that repo's own operational knowledge — its CI failures, its
  distillation sessions, its design choices — with zero dependency on
  knowing anything about the KB tool's internals. dotfiles' entries (e.g.
  `distill-session-into-memory`) are about dotfiles, not about
  knowledge-base.

Conflating the two pollutes whichever repo gets it wrong: KB-internal
trivia (e.g. "lint schema enforcement was added in Phase 6c") has no
business in a consumer repo's memory, and a consumer repo's operational
specifics (e.g. "dotfiles' CI job X failed because Y") have no business
being copied back into this repo's memory just because both happen to use
the same `kb.py`.

Rule of thumb: if an entry would stop being true after `scaffold.sh` copies
it elsewhere, it belongs in *this* repo's memory, not the consumer's — and
vice versa, if an entry only makes sense in the context of the consumer
repo's own codebase/history, it belongs there, not here.
