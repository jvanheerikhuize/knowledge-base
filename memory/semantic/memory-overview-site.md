---
name: memory-overview-site
type: semantic
description: this KB publishes itself as a static site to GitHub Pages, rebuilt on every push that changes memory content
confidence: verified
source: built 2026-07-27 in this repo — scripts/build_site.py and .github/workflows/pages.yml
created: 2026-07-27
last_verified: 2026-07-27
links: [kb-is-file-based, persist-insight-to-knowledge-base, editing-the-kb-without-a-cms, kb-entry-status-model, kb-timeline-and-heatmap-are-frontmatter-only]
---

The knowledge base has a browsable web overview, generated from `memory/`
itself — there is no second source of truth to keep in sync.

**Builder.** `python3 scripts/build_site.py [--out site]`, stdlib-only like the
rest of the tooling. It reuses `iter_entries()` and `parse_frontmatter()` from
`kb.py`, so the site sees exactly what the CLI and the linter see. It emits an
index with type filters and client-side search, one page per entry (frontmatter,
rendered body, resolved `[[wikilinks]]`, links out and backlinks), a Mermaid
graph page, a type reference page, a triage queue, and `site/data.json`.

**Editing.** The site is read-only when published and editable when served
locally by `scripts/serve.py` — one set of files either way. See
[[editing-the-kb-without-a-cms]] for why it works that way.

**`data.json` is the extension point.** It carries every entry in full —
frontmatter, body, resolved links, computed backlinks. Later interactivity
(timelines, graph exploration, editing) should be built against it rather than
by changing the builder.

**Publishing.** `.github/workflows/pages.yml` deploys to GitHub Pages on pushes
to `main` touching `memory/**`, `.kb/**`, `scripts/kb.py`, or the builder. Other
pushes do not redeploy, so a deploy means the memory itself moved. Lint runs
before the build, so a schema-invalid KB fails instead of publishing.

**Live at** https://jvanheerikhuize.github.io/knowledge-base/ — Pages is enabled
with `build_type: workflow`, so the workflow above is the only thing that
publishes; there is no branch-based build to keep in sync.

**Consequences to remember.** `site/` is git-ignored — never commit build
output. The repository is public, so everything in `memory/` is published to
the open web. Jerry has explicitly accepted this, so it is not a reason to
hesitate before storing something.
