---
name: purge-context-after-each-change
type: procedural
description: clear accumulated agent context after every completed change — Jerry's standing working preference, backed by lead/cycle-time evidence
confidence: verified
source: Jerry, 2026-07-14; settings verified in ~/.claude/settings.json on 2026-07-27
created: 2026-07-27
last_verified: 2026-07-27
links: [persist-insight-to-knowledge-base, asdlc-governed-change-rules]
---

Jerry asked (2026-07-14) that agent context be purged after every completed
change, not left to accumulate across a long session.

**Why.** He observed on his own metrics dashboard that changes made late in a
long-running session had visibly worse lead and cycle times than the same kind
of change made from a fresh context. Carried-over context also carries over
stale assumptions — which is exactly the failure mode this KB exists to fix.

**How to apply.**

1. Treat "change shipped" as the boundary. After a commit/PR lands, distill
   what's durable into this KB (see [[persist-insight-to-knowledge-base]]),
   then clear.
2. Prefer `/clear` for a hard reset when starting an unrelated change;
   `/compact` when continuing the same thread of work.
3. Rely on the written artefacts, not on remembered context — the KB entry,
   `PURPOSE.md`, the Change Record. If clearing would lose something, that
   something wasn't written down yet, so write it first.

**Automation already in place** (`~/.claude/settings.json`, added 2026-07-14
and still present 2026-07-27): `autoCompactEnabled: true`,
`autoCompactWindow: 100000`, and a `Stop` hook that nudges at the end of a
turn. The hook is a reminder, not a guarantee — the discipline is still
manual.

In `asdlc` this is not just a preference: decision D15 mandates purging agent
context between governed changes.
