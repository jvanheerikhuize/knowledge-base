---
name: asdlc-governed-change-rules
type: semantic
description: hard rules for working in asdlc and asdlc-verify — protected main, generated docs that must never be hand-edited, and Change Record id conventions
confidence: verified
source: distilled from session memory 2026-07-14; paths and CR-id format re-checked against the repo 2026-07-27
created: 2026-07-27
last_verified: 2026-07-27
links: [purge-context-after-each-change, workspace-audit-2026-07-27]
---

`~/Repos/asdlc` (spec + design) and `~/Repos/asdlc-verify` (Go verifier CLI)
are **public** repos implementing a governed, agent-/vendor-agnostic Agentic
SDLC framework, in a DORA + EU AI Act context. Rules that will break a session
if ignored:

**Main is protected.** Both repos have active rulesets: no direct pushes to
main, all changes via PR with required checks (`spec-check`, `g4-gate`), no
bypass even for the owner. Jerry has authorized merging green PRs in both
(recorded SoD exception).

**Never hand-edit generated docs.** Since `spec-v0.2.0`, `README.md`,
`PURPOSE.md`, and `docs/design/*.md` are generated from typed nodes in
`.asdlc/knowledge/` by `python3 spec/tools/scaffold.py`. CI fails on drift.
Edit the node (or the doc manifest), regenerate, commit both. To recall
context, read individual nodes (decisions, risks, status) — not whole docs.

**Change Records.** Governed changes need a Change Record plus an
`/asdlc approve <head-sha>` comment (see `bindings/github/README.md`). Since
spec 0.5.0 (D14), ids carry a 3-digit per-date sequence:
`CR-<yyyymmdd>-<seq>-<slug>`. Mint the next seq by listing `.asdlc/changes/`
for that date. The eight pre-0.5.0 ids are grandfathered — **never rename
them**, they are immutable evidence.

**Metrics are derived, never stored.** `spec/tools/metrics.py` computes
lead/cycle time. Evidence timestamps must come from the clock, never
hand-typed — the negative lead times in the 2026-07-14 CRs are the kept record
of that mistake.

**Other conventions.** Small known debts live as `leftover` nodes (generated
view: `LEFTOVERS.md`); "fix the leftovers" means one governed sweep change,
flipping fixed nodes to `status: done`. D15 mandates purging agent context
between changes — see [[purge-context-after-each-change]]. The four prior-art
repos (lifecycle/governance/orchestrator/swarm) are not on this machine; design
proceeds from the brief's §6 summary by intent.

**Stale detail, do not trust:** an earlier note pinned the resume point at
"CR-20260714-009 authored but not committed". `.asdlc/changes/` now runs
through `CR-20260716-005-exclude-negative-lead-bars`, so work continued past
that. `PURPOSE.md` is the authoritative state file — read it first.
