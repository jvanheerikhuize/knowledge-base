---
name: editing-the-kb-without-a-cms
type: semantic
description: browser Git CMSes all need an OAuth broker, so this KB edits through GitHub deep links plus a local server instead
confidence: verified
source: research + implementation 2026-07-27 — scripts/serve.py, scripts/build_site.py
created: 2026-07-27
last_verified: 2026-07-27
links: [memory-overview-site, kb-is-file-based]
---

**The finding.** No browser-based Git CMS can edit this knowledge base without
adding infrastructure. Decap CMS, Sveltia CMS, and TinaCMS were all evaluated;
each hits the same wall. GitHub's OAuth flow cannot complete from a purely
static page, because the token exchange needs a client secret, so every option
requires a broker you have to run and keep running:

| Option | What it forces you to add |
| --- | --- |
| Decap CMS | Netlify Identity, or a self-hosted OAuth proxy |
| Sveltia CMS | a Cloudflare Worker acting as the auth broker |
| TinaCMS | Tina Cloud (a hosted content API), or self-hosting it |

That is a service, a secret, and an availability dependency — exactly what
[[kb-is-file-based]] exists to avoid. The verdict: don't adopt one.

**What was built instead** — three layers, so each works where the one below
it cannot:

1. **Zero-auth affordances on the published site.** Every entry page carries an
   "Edit on GitHub" deep link (straight into GitHub's own editor, which handles
   auth itself) and a prefilled "Raise an issue" link. A `triage.html` page
   ranks entries needing attention using the same `triage_report()` the CLI
   reads. This works on GitHub Pages with no backend at all.
2. **`scripts/serve.py` for real editing.** A stdlib `http.server` that serves
   the built site plus a JSON API writing back into `memory/`. Run it locally
   and the same pages become an editor — description, confidence, links, and
   body, plus verify and delete — rebuilding after each write.
3. **CLI parity.** `kb.py triage / verify / set / link / edit / rm` performs
   every mutation the browser can. Both paths call the same helpers and both
   append to `.kb/log.md`, so neither can drift from the other.

**The mechanism worth remembering: progressive enhancement.** `build_site.py`
emits exactly one set of files. `app.js` probes `api/capabilities` on load; if
nothing answers, the page stays read-only, and if something does, the editing
UI is revealed. That is why GitHub Pages and the local editor can share one
artifact instead of needing two builds.

**The constraint this preserves.** Git stays the only durable write path. The
server edits the working tree, so changes are reviewable as a diff and land
through the normal branch-and-PR flow rather than being committed by a service
holding a token.
