---
name: workspace-repo-inventory-drift
type: semantic
description: workspace-repo rewrite (2026-08-06, jvanheerikhuize/repos) shipped its own submodule drift, fixed but still unmerged three-deep: #2 (this entry's eidolon/llm-wiki fix), #1 (an independent, overlapping fix of the same drift, opened first), #3 (ubunutu-cast typo) all open as of 2026-08-09
confidence: verified
source: 2026-07-27 filesystem enumeration (original finding, now historical); 2026-08-07 audit of jvanheerikhuize/repos' .gitmodules via git ls-remote per entry
created: 2026-07-27
last_verified: 2026-08-09
links: [persist-insight-to-knowledge-base, sibling-repo-access-denied-in-routines]
---

**Superseded structure, live finding.** The original claim below (a stale
`CLAUDE.md` table vs. a `~/Repos` filesystem) describes a workspace that no
longer exists in that form: sometime before 2026-08-07, the workspace was
rebuilt as `jvanheerikhuize/repos` (note the capitalization redirect —
`repos` → `Repos` — itself harmless), a git repo holding the other 24 repos
as **git submodules**, plus `AGENTS.md` (agent-agnostic entry point),
`CLAUDE.md`/`GEMINI.md` (thin pointers to it), `PURPOSE.md`, `ROADMAP.md`,
and `INTEGRATION.md`. `CLAUDE.md` claims "24 active repositories" and
`.gitmodules` lists exactly 24 — that count is not stale.

**What was still wrong, found 2026-08-07.** Cross-referencing every
`.gitmodules` URL against the live repo (`git ls-remote` on the recorded
URL, compared against the account's current repo list) found two of the 24
pointing at **pre-rename** repo URLs. GitHub redirects a renamed repo's old
URL automatically, so both still resolved — silently, which is exactly why
nobody had noticed:

- **`eidolon` → `undervault`.** Submodule path, section name, and URL all
  still said `eidolon`; `AGENTS.md`'s description ("Autonomous agent runtime
  & entity management framework") was the old repo's pitch, not the
  current one (a browser-based cinematic platformer — confirmed by the
  renamed repo's own README, which opens "*(formerly `eidolon`...)*").
- **`llm-wiki`'s URL said `asdlc-knowledge.git`** (pre-rename name; same
  repo, confirmed via matching HEAD/branch refs at both URLs). Path and
  section name were already correct.

Fixed in `jvanheerikhuize/repos#2` (`.gitmodules`, `AGENTS.md`,
`ROADMAP.md`'s P3 mention). Opened as a PR, not merged — the standing
cross-repo mandate says PR-only outside `knowledge-base`.

**The `knowledge` question, evidence not confirmation.** This entry's
original 2026-07-27 text guessed `llm-wiki` was the renamed `knowledge`
repo the old table cited, "not confirmed with Jerry." The 2026-08-07 finding
is adjacent evidence, not that confirmation: `llm-wiki` is itself a rename
of a repo called `asdlc-knowledge` (not `knowledge`) — plausible as the same
project under a still-different name, still not confirmed. `ROADMAP.md`'s
own P2 item already tracks this as open ("clarify scope"); it now carries a
note pointing at this finding.

**What this predicts about the next audit.** Both bugs were the same shape —
a rename whose redirect papered over the drift — which means `.gitmodules`
audits need to diff against live repo *names*, not just check that each URL
still resolves; a resolving-but-redirecting URL is exactly the failure mode
that hid both. Re-run this check periodically, since new renames will
reproduce it.

---

**Original finding (2026-07-27), for the record.** `~/Repos/CLAUDE.md`
claimed "20 active repositories" against 22 directories on disk: `knowledge`
was listed but absent (closest live repo `llm-wiki`, unconfirmed rename
guess — see above); `3d-printing`, `centauri-control`, and `llm-wiki` existed
on disk but were unlisted. That specific `CLAUDE.md`/filesystem pair no
longer exists to check — see "Superseded structure" above.

Checked back in on 2026-08-09: none of the three PRs this line of work opened have merged. jvanheerikhuize/repos#2 (this entry's fix), #3 (the ubunutu-cast typo fix), and a third, #1 ("chore: rename eidolon to undervault and add /name-sync", opened 2026-08-06T20:40Z, draft, by a session this store has no other record of), are all still open. #1 and #2 independently fix the identical eidolon->undervault and llm-wiki .gitmodules/AGENTS.md drift -- two sessions did the same audit because neither checked for an already-open PR before starting, the sibling-repo equivalent of this repo's own "check git ls-remote before picking a backlog item" rule, which the standing cross-repo mandate never asked for. Left both open rather than resolving the overlap unilaterally -- flagged on #2 instead, since merging both as-is conflicts on .gitmodules/AGENTS.md and choosing which one wins (#1 also ships a /name-sync drift-detection skill; #2 documents the audit in ROADMAP.md) is Jerry's call, not a session's.
