---
name: kb-entry-status-model
type: semantic
description: every KB entry sits in exactly one of eight statuses, worst-first, each naming the command that moves it — the answer to "what should I do about this entry"
confidence: verified
source: scripts/kb.py STATUS_MODEL and status_report(); implemented and tested 2026-07-27
created: 2026-07-27
last_verified: 2026-07-27
links: [kb-is-file-based, memory-overview-site, kb-agent-entrypoint-is-agent-md]
---

`kb.py triage` reports only what is already wrong, so a store where nothing
has ever been re-checked still reads as "clean". Freshness (`last_verified`)
and trust (`confidence`) are separate axes, and neither alone says what to do.

`kb.py status` closes that gap: it places **every** entry in exactly one of
eight states, worst first, so a single entry never produces a list of
competing complaints. Each state carries the literal command that leaves it.

| Status | Trigger | Remedy |
|---|---|---|
| `broken` | a frontmatter date will not parse | `kb.py set <name> last_verified YYYY-MM-DD` |
| `overdue` | prospective entry past its `due` date | act, then `set ... due` or `rm` |
| `stale` | `last_verified` older than 90 days | re-check, then `kb.py verify <name>` |
| `unverified` | never confirmed against a source | `kb.py verify <name> --confidence verified` |
| `provisional` | confidence `low` or `medium` | check directly, then `verify --confidence verified` |
| `isolated` | orphan or unlinked in the graph | `kb.py link <other-entry> <name>` |
| `ageing` | past 2/3 of the staleness cutoff | nothing yet; verify before `review_by` |
| `current` | recent, trusted, connected | nothing |

`review_by` = `last_verified` + 90 days, the date an entry falls to `stale`.
Exposing it turns maintenance from reactive (wait for triage to complain)
into scheduled.

The same model drives three surfaces from one definition: the CLI
(`status`, `--legend`, `--json`), the published site's `status.html` board
plus per-card badges, and `data.json` (`status`, `status_model`) — see
[[memory-overview-site]].
