---
name: workspace-improvement-phases
type: prospective
description: the P0–P6 improvement plan for ~/Repos, with each phase's status re-checked against the filesystem on 2026-07-27
confidence: high
source: plan authored 2026-07-24; completion status verified by direct inspection 2026-07-27
created: 2026-07-27
last_verified: 2026-07-27
links: [workspace-audit-2026-07-27, workspace-repo-inventory-drift]
---

Standing backlog for the workspace, ordered by priority. Statuses below come
from [[workspace-audit-2026-07-27]], not from the original plan document.

**P0 — Critical gaps.** *Done.* storyteller and Runbook-Gallery documented;
`.gitignore` added to nature-and-nurture and openSCAD; asdlc branch state
reconciled (local main is merely 3 commits behind origin now).

**P1 — Documentation & structure.** *Done for docs, partial for agent config.*
All 22 repos have README + PURPOSE.md. Roadmaps linked. The remaining piece is
P1.3: only 7 repos carry a `.claude/CLAUDE.md`, and knowledge-base's is
actively wrong (see [[kb-agent-entrypoint-is-agent-md]]).

**P2 — Knowledge consolidation.** *In progress — the current phase.*
- P2.1 digital-twin: finish collector patterns, validate wikilinks, integrate
  with this KB — under the constraint in [[twin-sovereignty-constraint]].
- P2.2 knowledge-base: 7-type taxonomy is formalized and linted; remaining
  work is an automated staleness audit.
- P2.3 the `knowledge` repo: the plan asks whether it merges with
  knowledge-base. It no longer exists under that name — resolve against
  `llm-wiki` first, see [[workspace-repo-inventory-drift]].
- P2.4 asdlc: formalize the knowledge taxonomy behind its generated docs.

**P3 — Games.** backrooms: convert `goal.md` into a structured `features/`
directory like just-in-time. just-in-time: write `MODDING.md`. E.C.H.O.:
implement session replay, test spectator isolation.

**P4 — System projects.** asdlc-verify: DSSE signatures and a tagged v0.1.0.
ubunutu-cast: finish the 6-phase rollout (quality flags, auth, tray). rss:
document the Ollama summarization model/caching/privacy story.
Runbook-Gallery: ship one real runbook end to end.

**P5 — Assets & reference.** openSCAD per-generator `CUSTOMIZATION.md`;
stencils `METADATA.json` provenance; Agent-Roles prompt recipes;
Powershell-Gallery health checks and alerts; dotfiles `PROFILES.md` matrix.

**P6 — Personal/experimental.** nature-and-nurture entry-metadata hook;
Autoinstall-YAML → dotfiles stage-1/stage-2 pipeline doc.

**Done when:** every repo has README + PURPOSE + ROADMAP and an appropriate
`.gitignore`; the knowledge repos are integrated rather than duplicated; game
repos have structured feature specs; system tools are at v0.1.0+; every repo
documents a clear next step.
