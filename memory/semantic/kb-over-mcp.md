---
name: kb-over-mcp
type: semantic
description: the KB is served to agents as MCP tools and resources over stdio, speaking 2025-11-25, with writes staged in the working tree and never committed
confidence: verified
source: scripts/mcp_server.py, tests/test_mcp_server.py, MCP spec 2025-11-25
created: 2026-07-28
last_verified: 2026-07-28
links: [kb-is-file-based, editing-the-kb-without-a-cms, kb-ranked-retrieval, kb-agent-entrypoint-is-agent-md, kb-prospective-memory-that-fires]
---

`scripts/mcp_server.py` serves this store over the Model Context Protocol on
stdio, stdlib-only, spawned by the client rather than kept running.
`.mcp.json` at the repo root registers it for any client that reads
project-scoped config.

**Six tools, all thin wrappers over kb.py's library functions.** `context`
(the budgeted brief — the call to make at the start of a task), `search`,
`get`, `triage`, `status`, and `propose_update`. Entries are additionally
published as resources at `kb://entry/<name>`, with `kb://agent` for
`memory/AGENT.md`, so a client can attach a document without a tool call.

**The stdout constraint shapes the code.** The stdio transport requires that
nothing but MCP messages reaches stdout, and that every message be a single
line. So the tools call `rank`, `context_pack`, `triage_report`,
`status_report` directly — never the `cmd_*` handlers, which print and
sometimes `sys.exit`. All server logging goes to stderr. `json.dumps` escapes
newlines inside strings, which is what keeps a multi-line entry body on one
line.

**Writes are proposals, and that is load-bearing.** `propose_update` edits the
working tree and stops; it never commits. Git remains the review gate and the
only durable write path — the same conclusion [[editing-the-kb-without-a-cms]]
reached for the browser, applied to the case where the writer is an agent
rather than a person. `--read-only` drops the tool from `tools/list` entirely,
which is the correct mode whenever the client is not yours. An agent using this
tool should report its change as *proposed*, not done.

**Protocol version: 2025-11-25, negotiating down to 2025-06-18 / 2025-03-26.**
The `2026-07-28` revision published the same day this shipped and is
deliberately not implemented. It deletes the `initialize` handshake in favour
of per-request `_meta`, adds `server/discover`, and states outright that there
is no automatic compatibility with `2025-11-25`. No client speaks it yet and
the SDKs are inside a ten-week validation window, so implementing it would have
traded a working server for a hypothetical one. The migration, when it comes,
touches only the lifecycle — the tool and resource surfaces are unaffected.
