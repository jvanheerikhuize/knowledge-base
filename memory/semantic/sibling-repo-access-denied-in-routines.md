---
name: sibling-repo-access-denied-in-routines
type: semantic
description: was true 2026-07-28 through 2026-08-06 — cloud routine sessions could only reach their configured repo. Reversed 2026-08-07: a broader GitHub grant (Jerry, standing mandate) now lets a session attach and push to any jvanheerikhuize/* repo via add_repo
confidence: verified
source: reprobed in the 2026-08-07 routine session — add_repo attached jvanheerikhuize/repos with push access, clone/push/PR all succeeded
created: 2026-07-28
last_verified: 2026-08-07
links: [holiday-autonomy-mandate, workspace-repo-inventory-drift, routines-ui-not-api-for-prompts]
---

**This entry's original claim no longer holds — corrected in place rather
than left standing, per [[kb-corrections-happen-in-place]].** Read
[[workspace-repo-inventory-drift]] for what the restored access was used for.

**What changed.** From 2026-07-28 through (at least) 2026-08-06, a cloud
routine session was scoped to exactly one repository — the one the routine
was configured with — and cloning or calling GitHub MCP tools against any
other `jvanheerikhuize/*` repo failed. The 2026-08-06 standing mandate
(recorded in `AUTONOMY.md`) said Jerry had granted broader access and told
future sessions to re-probe every run rather than trust the 2026-07-28
result indefinitely. The 2026-08-07 session did that: `list_repos` returned
all 36 `jvanheerikhuize/*` repos (not just `knowledge-base`), `add_repo`
attached `jvanheerikhuize/repos` with push access, `git clone`/`git push`
both worked, and a PR was opened against it
(`jvanheerikhuize/repos#2`). Cross-repo access is no longer the blocker.

**What still applies.** The *mechanism* recorded here is still correct and
worth knowing even though the *result* flipped: access is a property of how
the session's GitHub connector is scoped, not something a session can raise
by retrying — it changes only when a human (Jerry) changes the grant. That is
exactly what happened between 07-28 and 08-06. A future session finding
sibling access denied again should not assume this entry's "it works now" is
still true without re-probing — the same non-retryable-from-inside-the-session
property cuts both ways.

**Mechanics that now apply, for the next session that does this:**

- `mcp__Claude_Code_Remote__list_repos` — enumerates every repo the account's
  GitHub grant covers, `can_push` per repo.
- `add_repo(owner, repo, access: "push")` — attaches a repo to the session
  with write credentials; returns a clone command and a workspace path
  (typically `/workspace/<repo>`, case-normalized).
- `register_repo_root` after a successful clone — loads that repo's own
  `CLAUDE.md`/`AGENTS.md`/skills into context.
- The GitHub MCP server (`mcp__github__*`) only accepts calls against repos
  attached this way — `add_repo` first, GitHub MCP tools second.
- Per the standing mandate: PR the change, **do not merge it** — that
  authorization is scoped to `knowledge-base` during the (now-lapsed) holiday
  window, not renewed across the workspace.
