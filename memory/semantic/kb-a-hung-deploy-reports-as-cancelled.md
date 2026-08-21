---
name: kb-a-hung-deploy-reports-as-cancelled
type: semantic
description: the published site went twelve days without a deploy because one Pages run's deploy job hung queued and held the pages concurrency group — and the twelve runs that piled up behind it all reported `cancelled`, a conclusion that reads as deliberate rather than as a failure
confidence: verified
source: all 43 runs of .github/workflows/pages.yml queried 2026-08-21 (last success 2026-08-09T07:12:47Z, run 31301354176's deploy job queued since 2026-08-09T07:31:47Z with an empty pending_deployments list), and the successful deploy of 227f3fa immediately after that run was cancelled
created: 2026-08-21
last_verified: 2026-08-21
links: [memory-overview-site, kb-the-bundle-was-already-shipped, kb-the-backstop-arrives-after-the-session]
---

Found while checking CI on this session's own merge, which is the only reason
it was found at all.

**The published site had not been rebuilt since 2026-08-09.** Twelve days, and
across them every entry written for ROADMAP Phases 14 through 21 existed only in
the repository. [[memory-overview-site]] says the site is "rebuilt on every push
that changes memory content" and [[kb-the-bundle-was-already-shipped]] tells a
consumer that `data.json` is "published to Pages on every memory-touching push".
Both describe the design correctly. Neither was true of the running system.

## The mechanism

`pages.yml` carries the concurrency block GitHub's own Pages starter workflow
recommends:

```yaml
concurrency:
  group: pages
  cancel-in-progress: false
```

That is the right setting and it is not the defect: it exists so a production
deploy in flight is never killed by a newer push. What it assumes is that a
deploy in flight eventually *finishes*.

On 2026-08-09 one did not. Run `31301354176` built successfully and its
`deploy` job entered `queued` at 07:31:47Z and stayed there. It was not waiting
for a human — `pending_deployments` was empty, so no environment protection
rule was involved. It simply never ran, and because the group is never
cancelled in progress, it held the lock.

**Then the wreckage disguised itself.** With `cancel-in-progress: false`, GitHub
keeps at most one *pending* run per group: each new push supersedes the previous
waiting run and cancels it. So twelve consecutive daily runs — every one of them
a real, wanted deploy — ended with conclusion `cancelled`. That word reads as a
decision somebody made. Nothing in the repository distinguishes "cancelled
because a newer push superseded it" from "cancelled because the queue in front
of it is dead", and no green-or-red signal ever appeared, because a queued job
is neither.

The repair took one action: cancel the 2026-08-09 run. The queue drained
immediately and `227f3fa` deployed on the first attempt — the first successful
publish in twelve days.

## Why nothing caught it

This repo watches two things on a schedule (`kb-due.yml`, `kb-stranded.yml`) and
both open a tracking issue when they fire. Nothing watches the publish path.
The 2026-07-31 site-polish pass verified the *built output* against a local
build and the last successful deploy — a check that was correct then and would
have passed unchanged on any of the twelve broken days, because it never asked
whether a deploy had run since.

**A detector was deliberately not built.** One occurrence in 43 runs is a bug,
not a class, and this store's own rule is to wait for the third
([[kb-tests-cannot-cover-an-absent-guard]]); a watcher written now would be
scaffolding for a failure mode observed once. The reopen condition is recorded
in `ROADMAP.md`: build it on a second stall, and the predicate to use is
already known — the newest `pages.yml` run with conclusion `success` older than
the newest commit touching `memory/`, which is a two-request check and would
have fired on day one.

**What generalises** is the shape [[kb-the-backstop-arrives-after-the-session]]
records from the other direction. There, a backstop's *silence* was read as
evidence that nothing was wrong. Here, a queue's output was read as evidence
that somebody had decided something. Both are the same error: a status that a
system emits for several unrelated reasons carries no information about which
one, and treating it as if it does is how twelve days pass unnoticed.
