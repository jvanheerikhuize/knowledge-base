---
name: kb-agent-entrypoint-is-agent-md
type: semantic
description: memory/AGENT.md is the authoritative contract for knowledge-base; the repo's .claude/CLAUDE.md describes a layout that never shipped
confidence: verified
source: read both files and checked every path they name against the repo on 2026-07-27
created: 2026-07-27
last_verified: 2026-07-27
links: [kb-is-file-based, persist-insight-to-knowledge-base, kb-ranked-retrieval, holiday-autonomy-mandate]
---

`knowledge-base` has two documents claiming to tell an agent how to work in
the repo, and they contradict each other. **`memory/AGENT.md` is correct.**
`.claude/CLAUDE.md` is stale and describes an architecture that does not
exist on disk.

Every path `.claude/CLAUDE.md` names is wrong:

| It says | Reality |
|---|---|
| `types/` — memory type definitions | no such directory; types are folders under `memory/` |
| `templates/<type>/` — per-type templates | single shared template at `.kb/templates/entry.template.md` |
| `ci/lint.py` | `scripts/kb.py lint` |
| `ci/regenerate_graph.py` | no such script; the graph is a page of the published site, built by `scripts/build_site.py` |
| `ingestion/` | no such directory; use `scripts/kb.py new` |

The real layout: seven memory-type folders under `memory/`
(semantic, episodic, procedural, working, retrieval, parametric,
prospective), tooling in `scripts/` (`kb.py`, `build_site.py`, `serve.py`,
`scaffold.sh`), and machine-readable config in `.kb/` (`schema/`,
`templates/`, `log.md`). CI runs `.github/workflows/kb-lint.yml`.

An agent that follows `.claude/CLAUDE.md` will fail on its first command.
Until that file is rewritten or deleted, read `memory/AGENT.md` first. The
same file is also the source of the dangling reference to the nonexistent
`knowledge` repo — see [[workspace-repo-inventory-drift]].
