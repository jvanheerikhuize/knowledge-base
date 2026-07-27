---
name: workspace-repo-inventory-drift
type: semantic
description: the ~/Repos CLAUDE.md repo table is stale — 22 repos on disk, not the 20 documented, and one listed repo does not exist
confidence: verified
source: directly enumerated ~/Repos on 2026-07-27 and diffed against CLAUDE.md
created: 2026-07-27
last_verified: 2026-07-27
links: [persist-insight-to-knowledge-base]
---

`~/Repos/CLAUDE.md` claims "20 active repositories" and lists them in a
table. The filesystem disagrees — there are 22 directories, and the drift
runs in both directions:

**Listed but absent from disk:**

- `knowledge` — the "ASDLC knowledge base / LLM wiki pattern" row. No such
  directory exists. The closest live repo is `llm-wiki`, which is probably
  the same project after a rename, but this has not been confirmed with
  Jerry.

**Present on disk but absent from the table:**

- `3d-printing`
- `centauri-control`
- `llm-wiki`

Consequences: the workspace-level skills that iterate the table (`/repo-status`,
`/repo-audit`, `/sync-repos`) will silently skip the three unlisted repos if
they read CLAUDE.md rather than globbing the directory, and any agent
following the table will look for `knowledge/` and fail. `knowledge-base`'s
own `.claude/CLAUDE.md` (line 30 — not `memory/AGENT.md`, which is clean)
also tells agents to "keep wikilinks consistent across knowledge-base,
knowledge, and digital-twin" — a reference to the missing repo, and one more
count against that file per [[kb-agent-entrypoint-is-agent-md]].

The "Current state notes" section of the same file asserts "All 20 repos: on
main and clean" — treat that as a snapshot from an earlier session, not a
live fact.
