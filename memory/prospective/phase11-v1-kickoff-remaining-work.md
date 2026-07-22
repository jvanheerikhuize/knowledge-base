---
name: phase11-v1-kickoff-remaining-work
type: prospective
description: remaining items to close out Phase 11 (v1 kickoff) per docs/roadmap.md — ADOPTING.md, CHANGELOG + VERSION + v1.0.0 tag, version stamp in scaffolded copies
confidence: verified
source: docs/roadmap.md Phase 11 (p11a-e)
created: 2026-07-23
last_verified: 2026-07-23
links: [sync-fix-back-to-scaffolded-copies]
due: 2026-07-30
---

Phase 11 (v1 kickoff) per `docs/roadmap.md`, status as of 2026-07-23:

- **p11a** (entry gate) — merge the three open draft PRs: knowledge-base
  #8, knowledge-base #9, dotfiles #16. Not yet done as of this writing.
- **p11b** (CI step rename to reflect what lint actually checks) — done.
- **p11c** (not yet done) — write `docs/ADOPTING.md`: a ~10-minute
  end-user walkthrough for adopting this KB into a new repo, distinct from
  the existing "Scaffolding into another repo" README section (that's a
  command reference; ADOPTING.md should be a guided first-run).
- **p11d** (not yet done) — add `CHANGELOG.md` summarizing phases 0–10,
  stamp a `VERSION` file, tag `v1.0.0` on `main`.
- **p11e** (not yet done) — embed a version stamp in scaffolded copies
  (via `scaffold.sh`) so a consumer repo can detect drift against the
  source KB version, rather than only detecting it via manual diffing (see
  `sync-fix-back-to-scaffolded-copies`).

Revisit by the due date to check whether p11a's blocking PRs have merged
and whether p11c/d/e have been picked up.
