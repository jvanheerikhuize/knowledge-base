---
name: kb-entry-status-model
type: semantic
description: every KB entry sits in exactly one of ten statuses, worst-first, each naming the command that moves it — the answer to "what should I do about this entry"
confidence: verified
source: scripts/kb.py STATUS_MODEL and status_report(); implemented and tested 2026-07-27, extended 2026-07-28 (archived) and 2026-07-30 (contradicted)
created: 2026-07-27
last_verified: 2026-07-30
links: [kb-is-file-based, memory-overview-site, kb-agent-entrypoint-is-agent-md, kb-forgetting-model, kb-contradiction-is-a-second-axis, kb-prospective-memory-that-fires, kb-review-load-is-one-cohort]
---

`kb.py triage` reports only what is already wrong, so a store where nothing
has ever been re-checked still reads as "clean". Freshness (`last_verified`)
and trust (`confidence`) are separate axes, and neither alone says what to do.

`kb.py status` closes that gap: it places **every** entry in exactly one of
ten states, worst first, so a single entry never produces a list of
competing complaints. Each state carries the literal command that leaves it.

| Status | Trigger | Remedy |
|---|---|---|
| `contradicted` | another entry is judged to disagree with it | reconcile the two, then `kb.py judge <a> <b> <verdict> --agreement agree` |
| `broken` | a frontmatter date will not parse | `kb.py set <name> last_verified YYYY-MM-DD` |
| `overdue` | prospective entry past its `due` date | act, then `set ... due` or `rm` |
| `stale` | `last_verified` older than 90 days | re-check, then `kb.py verify <name>` |
| `unverified` | never confirmed against a source | `kb.py verify <name> --confidence verified` |
| `provisional` | confidence `low` or `medium` | check directly, then `verify --confidence verified` |
| `isolated` | orphan or unlinked in the graph | `kb.py link <other-entry> <name>` |
| `ageing` | past 2/3 of the staleness cutoff | nothing yet; verify before `review_by` |
| `current` | recent, trusted, connected | nothing |
| `archived` | retired from retrieval on purpose | nothing; `kb.py archive <name> --undo` puts it back |

Two of those are not properties of the entry's own frontmatter, and that is
deliberate. `isolated` is read off the link graph, and `contradicted` off
`.kb/verdicts.json` — an entry can be perfectly formed, freshly verified, and
still be one half of a pair that cannot both be true. `contradicted` sits
above `broken` because every other status means *nobody has checked*, while
this one means *somebody checked and the store is wrong*. See
[[kb-contradiction-is-a-second-axis]] for why nothing detects it automatically.

`review_by` = `last_verified` + 90 days, the date an entry falls to `stale`.
Exposing it turns maintenance from reactive (wait for triage to complain)
into scheduled.

The same model drives three surfaces from one definition: the CLI
(`status`, `--legend`, `--json`), the published site's `status.html` board
plus per-card badges, and `data.json` (`status`, `status_model`) — see
[[memory-overview-site]].
