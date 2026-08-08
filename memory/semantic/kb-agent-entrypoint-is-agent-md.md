---
name: kb-agent-entrypoint-is-agent-md
type: semantic
description: memory/AGENT.md is the authoritative contract for knowledge-base — a claim this store held correctly for twelve days while the two files contradicting it kept being injected into every session; both are now summaries that point at it
confidence: verified
source: read all three files and checked every path they name against the repo on 2026-07-27; re-checked and repaired 2026-08-08
created: 2026-07-27
last_verified: 2026-08-08
links: [kb-is-file-based, persist-insight-to-knowledge-base, kb-ranked-retrieval, holiday-autonomy-mandate, workspace-repo-inventory-drift, workspace-improvement-phases, kb-verification-rides-along-with-authoring]
---

**`memory/AGENT.md` is the authoritative contract** for how an agent works in
`knowledge-base`. Two other documents also claim that job, and both were wrong.
As of 2026-08-08 both are corrected and both now say, in their first lines,
that `AGENT.md` is the source and they are summaries.

**What `.claude/CLAUDE.md` used to say** (2026-07-27 → 2026-08-08). Every path
it named was wrong, and it was wrong in the most expensive possible place: a
`.claude/CLAUDE.md` is injected into every session in the repo, prefixed
`IMPORTANT: These instructions OVERRIDE any default behavior and you MUST
follow them exactly as written.`

| It said | Reality |
|---|---|
| `types/` — memory type definitions | no such directory; types are folders under `memory/` |
| `templates/<type>/` — per-type templates | single shared template at `.kb/templates/entry.template.md` |
| `ci/lint.py` | `scripts/kb.py lint` |
| `ci/regenerate_graph.py` | no such script; the site's graph page is built by `scripts/build_site.py` |
| `ingestion/` | no such directory; use `scripts/kb.py new` / `capture` |

It also carried the dangling reference to a `knowledge` repo that does not
exist under that name — see [[workspace-repo-inventory-drift]].

**A third entrypoint appeared on 2026-08-06.** `AGENTS.md` at the repo root
(commit `8830ee8`, "docs: add AGENTS.md and PURPOSE.md for multi-agent
support") described the store as four memory layers rather than seven types,
called the format "Markdown + JSON" when entries are Markdown with YAML
frontmatter, never mentioned `AGENT.md` at all, and pointed at
`/home/jerry/Repos/AGENTS.md` — an absolute path on one machine, rendered with
an `../AGENTS.md` href that resolves outside the repository, and describing a
workspace layout that had already been rebuilt as the submodule meta-repo
`jvanheerikhuize/repos`.

**Why it stood for twelve days is the part worth keeping.** This entry was
right from the day it was written, and said plainly "until that file is
rewritten or deleted, read `memory/AGENT.md` first." Nothing rewrote it.
[[workspace-improvement-phases]] carried the same instruction as open item
P1.3. The reason is not that anyone disagreed: `last_verified` on this entry
never moved, because it only moves when a session is already editing the entry
for some other reason, and no session had reason to edit this one. The claim
was correct, unread, and load-bearing for twelve days
([[kb-verification-rides-along-with-authoring]]).

**The real layout**, for the record: seven memory-type folders under `memory/`
(semantic, episodic, procedural, working, retrieval, parametric, prospective),
tooling in `scripts/` (`kb.py`, `build_site.py`, `serve.py`, `mcp_server.py`,
`scaffold.sh`), machine-readable config in `.kb/` (`schema/`, `templates/`,
`log.md`, `verdicts.json`, `golden.json`), tests in `tests/`, and workflows
`kb-lint.yml`, `kb-due.yml`, `pages.yml`.

**The standing rule.** Three files now describe this repo to an agent and only
one is authoritative. When the layout changes, `memory/AGENT.md` is the file
that must change; the other two are summaries and may lag. If they ever
disagree again, `AGENT.md` wins — and the disagreement is a defect to fix, not
a preference to weigh.
