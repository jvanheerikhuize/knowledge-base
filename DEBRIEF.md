# DEBRIEF — autonomous holiday work (2026-07-28 → 2026-08-05)

Jerry: this is everything shipped while you were away. **Triage by marking only
what you don't want** — tick a box (`[x]`) to flag an item for revert/discussion;
everything left unticked stands as-is. Each line links the commit or PR.

## How this ran

Daily cloud routine "Autonomy — daily workspace session" (Sonnet 5, 11:00
GMT+2) on `jvanheerikhuize/knowledge-base`, governed by [AUTONOMY.md](AUTONOMY.md).
Set up 2026-07-27 before you left.

## Shipped (mark only what you DON'T want)

- [ ] 2026-07-27 Autonomy charter + this debrief scaffold added (setup, this PR)
- [ ] 2026-07-28 **The KB is now an MCP server** — `scripts/mcp_server.py`, stdio, stdlib-only. Six tools (`context`, `search`, `get`, `triage`, `status`, `propose_update`) plus entries as `kb://entry/<name>` resources; `.mcp.json` registers it so any client in this repo picks it up with no setup. Writes are staged in the working tree and **never committed** — you review with `git diff`. `--read-only` drops the write tool entirely. 39 new tests (166 total, green). ROADMAP Phase 2 done.
- [ ] 2026-07-28 Implemented MCP **2025-11-25**, not the `2026-07-28` revision published the same day — it deletes the initialize handshake, has no automatic compatibility, and no client speaks it yet. Rationale and the migration path are in ROADMAP Phase 2; revisit when the SDKs ship.
- [ ] 2026-07-28 `scaffold.sh` now also copies `mcp_server.py`, so a KB scaffolded into another repo is agent-callable, not only a CLI.
- [ ] 2026-07-28 ROADMAP gained a **Sources consulted** section with real URLs and read-dates, and an explicit note that the near-neighbour projects cited in Phase 2 are *not* yet re-verified — flagged rather than papered over.
- [ ] 2026-07-28 Two KB entries: `kb-over-mcp` (the design and its constraints) and `sibling-repo-access-denied-in-routines` (see below).

## Blockers / notes

- **2026-07-28 — the session started read-only; you fixed it mid-run.** For most
  of this session `git push` returned 403 from the git relay and the GitHub API
  returned `403 Resource not accessible by integration`; reads worked
  throughout, so the credential was read-only rather than absent. You
  reconnected GitHub partway through and the push went straight out — the work
  above is on `claude/wizardly-dijkstra-idh56e`, nothing was lost. Worth
  remembering because the failure mode is quiet: a routine can do a full
  session of work, pass every test, and only discover at the end that it cannot
  push. Note for the record that the Claude GitHub App install is *not* what
  controls this — per the web docs, App installation drives PR webhooks and
  Auto-fix, while session git access comes from how the GitHub account is
  connected (web onboarding or `/web-setup`).

- **2026-07-28 — routine sessions cannot reach sibling repos.** Probed
  directly: cloning `jvanheerikhuize/digital-twin` fails on auth, and the
  GitHub MCP tools refuse any repo other than `knowledge-base`. This is how the
  routine is scoped, not something a session can raise. **Consequence:** the
  workspace-docs-drift item (`~/Repos/CLAUDE.md` lists 20 repos, disk has 22)
  cannot be done from here, and neither can any other cross-repo work — it is
  now marked blocked in `AUTONOMY.md` rather than left to be re-attempted every
  session. **If you want autonomous work happening in other repos, configure
  one routine per repo** the same way this one was set up.
