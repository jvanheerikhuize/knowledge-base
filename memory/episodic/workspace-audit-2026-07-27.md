---
name: workspace-audit-2026-07-27
type: episodic
description: filesystem-verified audit of all 22 repos in ~/Repos on 2026-07-27 — documentation coverage, dirty trees, and which stored claims it falsifies
confidence: verified
source: direct inspection — ls, git status, git rev-list, gh pr view across every repo on 2026-07-27
created: 2026-07-27
last_verified: 2026-07-27
links: [workspace-repo-inventory-drift, workspace-improvement-phases, twin-sovereignty-constraint, asdlc-governed-change-rules]
---

Ran a full sweep of `~/Repos` on 2026-07-27 while migrating accumulated
session memory into this KB. Every claim below was checked against the
filesystem or `git`/`gh` output, not carried over from an earlier note.

**Inventory.** 22 repos, all on `main`. The workspace `CLAUDE.md` table lists
20 — details in [[workspace-repo-inventory-drift]].

**Documentation coverage.** All 22 have both `README.md` and `PURPOSE.md`.
Only 7 have a `CLAUDE.md`: Autoinstall-YAML, asdlc, backrooms, digital-twin,
just-in-time, knowledge-base, llm-wiki.

**Uncommitted work.**

| Repo | State |
|---|---|
| llm-wiki | 81 uncommitted **deletions** under `.asdlc/knowledge/**` |
| asdlc | untracked `.claude/` |
| ubunutu-cast | untracked `.claude/` |
| 3d-printing | modified `models/mahjong/export/man9-back.3mf` |
| stencils | 2 untracked images under `Stencils/Bombing Beetle/` |

The llm-wiki deletions are large and unexplained — worth confirming with
Jerry before anything else touches that repo, in case they were accidental.

**Behind origin/main** (none ahead): ubunutu-cast 9, asdlc 3, action-rsi 2,
asdlc-verify 1, openSCAD 1. asdlc's locally-missing `.gitignore` is explained
by this: PR #29 ("chore: add .gitignore to exclude Claude artifacts") merged
2026-07-25 and hasn't been pulled.

**Corroborations.** `digital-twin/docs/SOVEREIGNTY.md` exists. In asdlc,
`.asdlc/knowledge/`, `.asdlc/changes/`, and `spec/tools/scaffold.py` all
exist as documented; the newest Change Records are `CR-20260716-002` through
`-005`.

**Stored claims this falsifies.** Prior session memory dated 2026-07-24 said
"19/20 README, 1/20 PURPOSE.md" and "all 20 repos on main and clean". The
documentation figures are now better than that (22/22 on both — the P1
documentation phase is genuinely complete), and the cleanliness claim is
false: five repos are dirty and five are behind. The workspace `CLAUDE.md`
"Current state notes" section still asserts the clean/20-repo version.
