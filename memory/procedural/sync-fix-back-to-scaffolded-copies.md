---
name: sync-fix-back-to-scaffolded-copies
type: procedural
description: how to propagate a kb.py/visualize.py fix made in this repo out to repos that scaffolded a copy, since scaffold.sh copies files once with no ongoing link
confidence: verified
source: Phase 9b friction item 3; precedent = dotfiles PR #14 (merged)
created: 2026-07-23
last_verified: 2026-07-23
links: [self-knowledge-vs-scaffolded-consumer-knowledge]
---

`scaffold.sh` copies `memory/`, `scripts/kb.py`, `scripts/visualize.py`, and
the CI workflow into a target repo once — it does not leave any link back
to this repo, so a fix made here (e.g. the Phase 6c lint-schema-enforcement
fix) does not reach scaffolded copies automatically. Real precedent: that
exact fix had to be manually diffed and re-copied into dotfiles as
dotfiles PR #14 (merged).

Steps to sync a fix into a scaffolded copy:

1. In this repo, confirm the fix is on `main` and identify which files
   changed (usually just `scripts/kb.py` and/or `scripts/visualize.py` —
   never `memory/` contents or `.kb-config`, which are the consumer's own
   data).
2. In the target repo, either:
   - add this repo as a remote once and selectively checkout the changed
     files (`git remote add kb-upstream <url>`, `git fetch kb-upstream`,
     `git checkout kb-upstream/main -- scripts/kb.py scripts/visualize.py`), or
   - do a one-off `curl` of the raw file(s) from this repo's `main`, or
   - if the target repo wants it automated, set up a scheduled sync
     workflow (e.g. `actions-template-sync`) that opens a PR on upstream
     changes.
   (All three options are documented in this repo's own README, "Keeping a
   scaffolded copy in sync".)
3. **If `scripts/visualize.py` changed**, regenerate the graph immediately
   after copying it — a generator change can alter output format without
   any `memory/` content changing, so the committed graph silently goes
   stale relative to what CI's `kb-lint.yml` staleness check expects:
   ```bash
   python3 scripts/visualize.py
   git add memory/_generated/graph.md memory/_generated/graph.mmd
   ```
4. Run `python3 scripts/kb.py lint` in the target repo to confirm the
   synced tool still passes against the target's existing entries.
5. Commit and open a PR in the target repo (small, focused commit — this is
   a tooling sync, not a content change, so keep it separate from any
   `memory/` entry additions).
