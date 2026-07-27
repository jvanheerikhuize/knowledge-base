---
name: routines-ui-not-api-for-prompts
type: semantic
description: the claude.ai RemoteTrigger API cannot set a routine's instructions or environment — both silently fail; only the Routines UI can, where model, repo, and connectors are also chosen
confidence: verified
source: direct API probing + UI configuration of trig_01C7kPrEFEAyf68bmfZE7wKZ, 2026-07-27
created: 2026-07-27
last_verified: 2026-07-27
links: [holiday-autonomy-mandate]
---

Empirical findings from configuring the autonomous-week routine (2026-07-27):

**The RemoteTrigger API is schedule-only in practice.** It can create/list/
update/run triggers and manage `name`, `cron_expression` (UTC), and `enabled`,
but:

- `initial_prompt` / `prompt` / `session_context.initial_prompt` inside
  `job_config.ccr` return HTTP 200 and are **silently dropped** — unknown
  fields are discarded without error, and the UI then shows "No prompt set".
- Every variant of `session_request.worker` fails 400 "Field required" — the
  union is unparseable through the wrapper.
- A repo slug (e.g. `jvanheerikhuize/knowledge-base`) is accepted as
  `environment_id` at write time but `run` then fails 400
  `environment_not_found`, and a failed run **auto-disables** the trigger
  (`ended_reason: auto_disabled_env_not_found`).

**The Routines UI (claude.ai/code/routines) is the real configuration
surface.** Its edit dialog sets: instructions, repository (picker over all
GitHub-app repos), **model per routine** (Default/Fable 5/Opus 5/Sonnet 5/
Haiku 4.5/Opus 4.x — so research-vs-execution tiering works), connectors
(default includes Gmail/Calendar/Drive with unprompted write access — strip
to Claude_Code_Remote for unattended runs), an "Auto-fix pull requests"
behavior toggle, and schedule shown in local time (Jerry is GMT+2; cron is
stored UTC).

Practical recipe: create/adjust schedules via API if convenient, but set
instructions + repo + model + connectors in the UI, and keep routine
instructions to a short pointer at a charter file in the repo — long
imperative instruction texts can be rejected, and the repo file is
versioned anyway.
