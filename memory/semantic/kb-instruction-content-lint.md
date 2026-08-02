---
name: kb-instruction-content-lint
type: semantic
description: unlike Phase 4's validity-interval detector (244 fires, 0 true positives), a cheap regex union for prompt-injection-shaped content measured real signal — 7 of 9 planted attacks caught with 0 false positives on the real store — so ROADMAP Phase 10 shipped it, plus an authority field the same measurement pass showed was already needed
confidence: verified
source: measured 2026-08-02 in this repo; ROADMAP Phase 10
created: 2026-08-02
last_verified: 2026-08-02
links: [kb-over-mcp, asdlc-governed-change-rules, twin-sovereignty-constraint, purge-context-after-each-change, kb-corrections-happen-in-place]
authority: rule
---

ROADMAP Phase 10 asked three things, on the premise that a store served to
agents over MCP is an injection surface. All three were measured before being
built, the same discipline Phase 4 through 7 used — and this time the
"measure before building" step said **build it**, which had not happened yet
in this series.

## The lint check has real signal — unlike Phase 4's detector

Five candidate detectors were run against two corpora: the store's 29 real
entries (no adversary in it — the honest starting condition Phase 10 itself
warned about) and 9 planted attack payloads written the way a real
prompt-injection attempt reads (direct override, fake authorization, a
hidden HTML comment, a jailbreak persona, credential exfiltration via a
backticked shell command, a "trusted reviewer" spoof).

| detector | true positives (of 9) | false positives (of 29) |
|---|---|---|
| imperative-sentence density | 3 | 2 |
| second-person directive (`you must`) | 2 | 0 |
| override phrase (`ignore previous instructions`, `sole source of truth`) | 5 | 0 |
| hidden HTML comment | 1 | 0 |
| destructive command inside a code span | 1 | 0 |
| **union of the four zero-FP signals** | **7** | **0** |

Imperative-sentence density was dropped — it fired on this store's own
procedural entries (`distill-session-into-memory`,
`persist-insight-to-knowledge-base`), which are legitimately full of
imperatives ("Run…", "Never…", "Always…"). The other four, unioned, catch
7 of 9 attacks with zero false positives on real content. The two misses are
an honest limit, not chased by widening the patterns: a base64-obfuscated
payload (regex reads text, not decoded intent) and an override phrase worded
differently from the patterns tried (`"supersedes AUTONOMY.md and all other
memory"` vs. the `supersedes? (all|any) other` pattern — the same
negation/ordering brittleness [[kb-contradiction-is-a-second-axis]] found in
Phase 3's contradiction detector). Widening the phrase list to catch it was
tried and rejected: the store discusses its own git governance in plain
prose (`force-push`, `safety checks`) using the same vocabulary an attack
would, so a broader net starts flagging `holiday-autonomy-mandate` for the
line "Never force-push."

**Shipped:** `kb.py lint` now flags matches as warnings (fatal only under
`--strict`, the weekly cron). All four signals skip inline/fenced code
spans, so an entry documenting the attack phrases as examples — this one —
does not flag itself; `destructive-command` inverts that and only looks
*inside* code spans, since a bare command only matters as something meant to
run. 6 new tests, including one asserting this store's own procedural
imperatives ("Run `kb.py lint`... Never force-push...") stay clean.

## The rule-vs-preference gap was already live, not hypothetical

Phase 10's second bullet worried that "a preference cannot be read as a
rule." Checking whether that was already a real ambiguity, not a
hypothetical one, took reading three existing entries side by side:

- [[asdlc-governed-change-rules]] — "hard rules... that will break a session
  if ignored."
- [[twin-sovereignty-constraint]] — "a standing, non-negotiable design
  constraint."
- [[purge-context-after-each-change]] — its own description already says
  "Jerry's standing **working preference**."

All three are phrased with identical imperative grammar ("Jerry asked",
"Jerry set", "must") and identical frontmatter shape. Nothing distinguished
a constraint that breaks CI from a habit that can be skipped for good
reason — an agent had to read prose carefully, every time, to tell them
apart, and the prose itself does not mark the difference.

**Shipped:** an optional `authority: rule | preference` frontmatter field,
left unset for the other 26 entries (most content is neither). `kb.py
search` and `kb.py context` now show it as `[RULE]` / `[preference]` next to
the entry — the context pack is what an agent actually acts on, so that is
where the distinction has to surface, not just in frontmatter nobody reads.
The three entries above are tagged; this one is too, since a lint rule that
can go strict-fatal in CI is itself binding. `kb.py lint` validates the
value (typo'd `authority` is a hard error, not a silently-ignored field).
5 new tests.

## Third bullet: `.kb/log.md` was already complete data, just unreadable

The mutation log Phase 2 shipped already records every create/verify/link/
archive/delete. The gap was presentation, not data: an append-only file read
bottom-to-top. `kb.py log [--limit] [--type] [--action] [--name] [--json]`
reads it back most-recent-first and filterable; `changes.html` on the site
does the same for a browser. Neither is a second record — `.kb/log.md` (and
under it, git) still is. 10 more tests (site + CLI).

## What this does not claim

The 0-false-positive number is measured against a single-author, single-agent
store with no adversary in it, same caveat Phase 10 itself raised. It says
the *signal* is real on content shaped like these 9 attacks, not that the
check catches every injection technique — determined obfuscation (the
base64 miss) defeats any regex lint by construction. This is a tripwire for
crude, easy-to-write injection, reviewed by a human on a `--strict` failure,
not a security boundary.
