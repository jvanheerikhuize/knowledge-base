---
name: sibling-repo-access-denied-in-routines
type: semantic
description: cloud routine sessions can only reach the repo they were configured for — sibling jvanheerikhuize/* repos cannot be cloned, so autonomous work stays in one repo per routine
confidence: verified
source: probed directly in the 2026-07-28 routine session (git clone of a sibling repo)
created: 2026-07-28
last_verified: 2026-07-28
links: [holiday-autonomy-mandate, workspace-repo-inventory-drift, routines-ui-not-api-for-prompts]
---

A cloud routine session is scoped to exactly one repository: the one the
routine was configured with. Sibling repos under the same account are not
reachable.

**What was tried.** `git clone https://github.com/jvanheerikhuize/digital-twin.git`
from inside the routine session. It failed at authentication —
`could not read Password for 'http://local_proxy@...': terminal prompts
disabled`. The session's GitHub credentials are scoped to
`jvanheerikhuize/knowledge-base` alone; the same scope applies to the GitHub
MCP tools, which refuse calls targeting any other repo.

**What follows.** Cross-repo work cannot be done from one routine. Two
consequences worth remembering:

- Backlog items that need another repo (the `~/Repos/CLAUDE.md` inventory
  reconciliation in [[workspace-repo-inventory-drift]], anything in the
  workspace ROADMAP outside this repo) are **not blocked on effort, they are
  blocked on access**. Do not re-attempt them from a routine; record and skip.
- To get autonomous work happening in another repo, configure a separate
  routine pointed at that repo — the same way this one was set up through the
  UI, per [[routines-ui-not-api-for-prompts]]. One routine per repo is the
  unit, not one routine per workspace.

This is a property of how the routine is scoped, not a permission that can be
raised from inside the session, so no amount of retrying changes it.
