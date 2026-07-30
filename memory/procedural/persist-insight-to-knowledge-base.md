---
name: persist-insight-to-knowledge-base
type: procedural
description: standing convention — durable knowledge from any session lands in the knowledge-base repo, not only in per-project auto-memory
confidence: verified
source: Jerry, session 2026-07-27
created: 2026-07-27
last_verified: 2026-07-27
links: [distill-session-into-memory, kb-is-file-based, workspace-repo-inventory-drift, kb-agent-entrypoint-is-agent-md, audit-test-corpora-for-artificial-uniformity]
---

Jerry's standing instruction: this repo is the store of record for knowledge
and insight collected while working anywhere in `~/Repos`. Consult it before
starting work, and write back to it afterwards. Per-agent auto-memory (e.g.
`~/.claude/projects/*/memory/`) holds only working preferences and a pointer
here — it is not the durable store.

Steps:

1. **Before work.** Run `scripts/kb.py search "<topic>"` and
   `scripts/kb.py list` to pull existing context. Read `memory/AGENT.md`
   first if unfamiliar with the layout — it, not `.claude/CLAUDE.md`, is the
   authoritative contract (see [[kb-agent-entrypoint-is-agent-md]]).
2. **During work.** When a task needs reference content — conventions,
   inventories, prior decisions — source it from `memory/` rather than
   re-deriving it, and correct the entry in place if reality has drifted.
3. **After work.** Classify each new durable finding into one of the 7
   memory types and scaffold it:
   `scripts/kb.py new --type <type> "<slug>"`. Follow
   [[distill-session-into-memory]] for the distillation pass.
4. **Set `confidence` honestly** per the rubric in `memory/AGENT.md`. Facts
   checked directly against a filesystem, command output, or primary doc are
   `verified`; anything taken on a single unconfirmed report is at most
   `high`.
5. **Validate before committing.** `scripts/kb.py lint` must be clean, and
   `scripts/kb.py triage` should surface nothing new after a batch of
   additions. The published overview rebuilds itself from `memory/` on push —
   there is no generated file to refresh by hand.

Do not persist what the repo already records (code structure, git history)
or what matters only to one conversation. Prefer updating an existing entry
over creating a near-duplicate slug.
