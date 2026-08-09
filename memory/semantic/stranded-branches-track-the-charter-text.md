---
name: stranded-branches-track-the-charter-text
type: semantic
description: routine sessions leave work unlanded at a rate set by what AUTONOMY.md authorizes, not by which routine is running — 0 of 11 while automerge was pre-authorized, 3 of 6 after it was withdrawn with no replacement named
confidence: verified
source: replayed all 23 routine sessions with evidence (merged PR or surviving branch) against the two commits that changed AUTONOMY.md's landing rules, 2026-08-09
created: 2026-08-09
last_verified: 2026-08-09
links: [kb-archived-is-a-filter-commands-forget, sibling-repo-access-denied-in-routines, kb-tests-cannot-cover-an-absent-guard]
---

A routine session "strands" work when it pushes a branch and ends without the
work reaching `main`. `AUTONOMY.md` has treated this as a discipline problem
since 2026-07-31 — "a branch that is pushed and left is invisible" — and
addressed it with a prose rule. Measured across every routine session this repo
has a record of, the rule is not the variable. **What the charter authorizes
is.**

## The measurement

One row per routine session with evidence: a `claude/*` head branch that either
produced a merged PR or still sits on the remote. 23 sessions, 2026-07-28
through 2026-08-08. Two commits move the boundary:

- **R** — 2026-07-31 08:08 UTC (PR #30). "End every session with the work on
  `main`, or with the reason it is not" enters the charter.
- **P** — 2026-08-05 09:20 UTC (PR #43). The post-mandate section withdraws the
  holiday blanket pre-authorization for "large chunks" and **"automerge"**.

| window | sessions | stranded | |
|---|---|---|---|
| A — before the rule | 6 | 2 | 33% |
| B — rule present, automerge authorized | 11 | **0** | **0%** |
| C — rule present, automerge withdrawn | 6 | **3** | **50%** |

B vs C, Fisher exact one-sided: **p = 0.029**. The rule alone held eleven
sessions for eleven. It stopped holding the day the authorization behind it was
taken away.

**The obvious confound is not it.** The 09:xx execution routine stranded 4 of
11 and the 07:xx research routine 1 of 12 — p = 0.13, not distinguishable, and
both tiers appear in window C. Every session in window B landed its work,
including six 09:xx ones.

## Why, in the sessions' own words

This is not inferred from the rate. Both 2026-08-06 sessions wrote the reason
down. `claude/wizardly-dijkstra-0sq8ef` held a real `lint` fix with a hard
deadline — the weekly `--strict` cron would have gone red on 2026-08-10 — and
the session

> deliberately did **not** merge it to `main` or self-close it, reasoning that
> the "end every session on `main`"/automerge pre-authorization was scoped to
> the mandate period, and pinning the fix to a branch for Jerry's own action
> was the more conservative reading.

That is a session naming the contradiction and resolving it the losing way. As
written, the two rules cannot both be satisfied: one says end on `main`, the
other says the way you get there is no longer pre-authorized, and **no third
option is written down.** A session that reasons carefully still ends with the
work off `main`.

**And the error propagates.** The next session (`claude/cool-cerf-4c7ia8`,
same day) found that branch, confirmed the defect was still live, and then
"left the branch and that decision exactly as found rather than overriding a
prior session's considered call by merging it unilaterally" — before stranding
its own note the same way. A stranded branch reads to the next session as
evidence of a judgement, not as a symptom, so deferring to it is the polite and
wrong move. The fix waited until 2026-08-07, three days from its deadline, and
was recovered only because a session went looking.

## The cleanup story was also wrong

The charter records that these branches accumulate because "a routine session
cannot delete a remote branch" — `git push origin --delete` dies with
`send-pack: unexpected disconnect while reading sideband packet`. That is true,
and re-confirmed a third time on 2026-08-09.

It is not why the litter exists. This repo has **delete-branch-on-merge**
enabled: all 18 `claude/*` branches that were merged *through a GitHub PR* were
deleted automatically, and every branch that survived is one no PR ever merged.
Merging PR #51 on 2026-08-09 deleted `claude/cool-cerf-712ymx` on the spot,
which is the check.

So the rule is not "ask Jerry to delete branches." It is **land the work by
merging its PR and there is no branch to delete.** Only the four already-dealt-
with leftovers still need `push --delete`, and two of those are 0 commits ahead
of `main` — pure ref litter that cannot even be PR'd, because a PR needs a
diff.

## What this means for a session reading this

- Ending with work off `main` is the failure the charter names, and it is the
  one thing measurement says sessions actually do wrong.
- If landing routine maintenance seems unauthorized, that reading has been
  tested three times and cost a live fix three days. The post-mandate section's
  own next sentence — "routine, low-risk maintenance is still fine without
  asking... that standing permission does not expire" — is the governing one.
  The withdrawal is a gate on *starting* new large-scope work, not on *landing*
  work already done.
- A leftover `claude/*` branch is a symptom to recover, not a decision to
  respect. Read the branch, not the fact that it was left.
