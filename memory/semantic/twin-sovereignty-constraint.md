---
name: twin-sovereignty-constraint
type: semantic
description: digital-twin must stay usable with no vendor LLM, no API key, and no agent in the loop — a standing, non-negotiable design constraint
confidence: verified
source: Jerry, 2026-07-12; corroborated by digital-twin/docs/SOVEREIGNTY.md
created: 2026-07-27
last_verified: 2026-07-27
links: [workspace-audit-2026-07-27]
authority: rule
---

Standing constraint Jerry set on `~/Repos/digital-twin` (private repo
`jvanheerikhuize/digital-twin`) on 2026-07-12: **he must not need Claude, any
LLM, or any agent in order to talk to his own twin.**

**Why.** A twin of yourself that only works while a vendor serves a model and
a card keeps clearing is rented, not owned. This became concrete during the
build — his Anthropic key ran out of credit mid-session and the first version
crashed rather than degrading.

**How to apply.** Every feature added to that repo must keep the bottom tier
working with no model at all:

- corpus stays plain JSONL
- retrieval stays stdlib-only BM25
- the package keeps zero required dependencies (`anthropic` is an optional
  extra)
- `twin recall` always returns his own words verbatim, without an LLM
- providers form a fallback chain (anthropic → ollama → none) that degrades at
  *request* time, not just at startup

Do not propose designs that make a vendor load-bearing. If a feature needs a
model, it needs a no-model path too. The rationale is written up in that
repo's `docs/SOVEREIGNTY.md` (confirmed present 2026-07-27).
