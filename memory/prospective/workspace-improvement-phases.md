---
name: workspace-improvement-phases
type: prospective
description: the P0–P6 improvement plan for ~/Repos, with each phase's status re-checked against the filesystem on 2026-07-27
confidence: high
source: plan authored 2026-07-24; completion status verified by direct inspection 2026-07-27
created: 2026-07-27
last_verified: 2026-08-23
links: [workspace-audit-2026-07-27, workspace-repo-inventory-drift, kb-roadmap]
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
- P2.2 knowledge-base: *done.* 7-type taxonomy formalized and linted, and the
  staleness audit shipped — `kb.py triage`, `lint --strict`, and a weekly cron
  in `.github/workflows/kb-lint.yml`. Further work is tracked in its own
  ROADMAP.md via [[kb-roadmap]], not here.
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

**Re-verified 2026-08-23, against a fresh clone of `jvanheerikhuize/repos`.**
This plan predates the 2026-08-06/07 workspace rebuild into a git-submodule
meta-repo ([[workspace-repo-inventory-drift]]) and is now superseded, not
current: that repo carries its own `ROADMAP.md`, rewritten with a different
phase scheme (P1 "Documentation & Agent-Agnostic Foundation" — folding this
plan's P0+P1 — marked **✓ COMPLETED**, including "PURPOSE.md across all 24
workspace repositories" and "AGENTS.md or agent specs across all
repositories"; P2 knowledge consolidation still "in progress", matching this
entry). Submodules are not checked out in a non-recursive clone, so the P1.3
`.claude/CLAUDE.md`-count claim above could not be re-checked at the
filesystem level and is left as an open question rather than confirmed either
way. What *could* be checked: the two P2.3-adjacent naming fixes are still
unlanded — `jvanheerikhuize/repos` PRs
[#1](https://github.com/jvanheerikhuize/repos/pull/1) (2026-08-06),
[#2](https://github.com/jvanheerikhuize/repos/pull/2) (2026-08-07), and
[#3](https://github.com/jvanheerikhuize/repos/pull/3) (2026-08-08) are all
still open and unreconciled 15–17 days later, and `.gitmodules` on `main`
still reads `[submodule "eidolon"]` (not `undervault`) and
`[submodule "ubunutu-cast"]` (not `ubuntu-cast`) — so "P1 done" overstates
completion at these two known points. Landing those PRs is Jerry's call, not
a routine's (per the standing mandate's cross-repo rule); this entry just
records that "done" and "actually merged" have diverged here.
