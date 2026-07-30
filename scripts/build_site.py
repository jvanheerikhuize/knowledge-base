#!/usr/bin/env python3
"""Static site layer: renders memory/ into a browsable site under site/.

No third-party dependencies — stdlib only, same as the rest of the KB tooling.
Output is self-contained apart from the Mermaid script on the graph page.

    python3 scripts/build_site.py [--out site]

The build also emits `site/data.json`, the full entry set as structured data.
The client-side search reads it, and it is the intended hook for making the
overview interactive later without changing the builder.
"""
import argparse
import html
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.parse
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from kb import (  # noqa: E402
    ROOT,
    STATUS_BY_KEY,
    STATUS_MODEL,
    STATUS_ORDER,
    TYPES,
    iter_entries,
    parse_frontmatter,
    status_report,
    triage_report,
)

DEFAULT_OUT = ROOT / "site"

# Branch the "edit on GitHub" deep links point at.
EDIT_BRANCH = os.environ.get("KB_BRANCH", "main")

TRIAGE_BLURB = {
    "overdue": "past its <code>due</code> date",
    "invalid-due": "unparseable <code>due</code> date",
    "invalid-date": "unparseable <code>last_verified</code> date",
    "stale": "not verified recently",
    "unverified": "still <code>unverified</code> well after it was written",
    "never-verified": "never verified",
    "orphan": "nothing links to it",
    "unlinked": "links to nothing",
}

TYPE_COLORS = {
    "semantic": "#2e7d32",
    "episodic": "#1565c0",
    "procedural": "#6a1b9a",
    "working": "#8d6e63",
    "retrieval": "#00838f",
    "parametric": "#455a64",
    "prospective": "#ef6c00",
}

TYPE_BLURB = {
    "semantic": "Facts and concepts — what is true, independent of when it was learned.",
    "episodic": "Specific events — what happened, when, and what was observed.",
    "procedural": "How to do things — conventions, workflows, and standing instructions.",
    "working": "Short-lived scratch state for work currently in flight.",
    "retrieval": "Pointers to where knowledge lives rather than the knowledge itself.",
    "parametric": "Tuning values, thresholds, and configuration worth remembering.",
    "prospective": "Intentions and commitments — what is meant to happen next.",
}

CONFIDENCE_ORDER = ["verified", "high", "medium", "low", "unverified"]

STATUS_COLORS = {
    # The worst state in the model, and the only one where the store is
    # actively wrong rather than merely unchecked — hence the strongest colour.
    "contradicted": "#880e4f",
    "broken": "#b71c1c",
    "overdue": "#c62828",
    "stale": "#ef6c00",
    "unverified": "#f9a825",
    "provisional": "#f9a825",
    "isolated": "#6a1b9a",
    "ageing": "#0277bd",
    "current": "#2e7d32",
    # Retired on purpose — greyed rather than coloured, so it reads as
    # "out of play" instead of as another thing needing attention.
    "archived": "#616161",
}


# --------------------------------------------------------------------------
# GitHub deep links — the zero-infrastructure half of "interact with the site"
# --------------------------------------------------------------------------

def repo_slug(explicit=None):
    """owner/name for this repo, so pages can link into GitHub's own editor.

    Explicit flag wins, then $KB_REPO, then the origin remote. Returns None
    when nothing resolves, and every GitHub affordance is then omitted rather
    than rendered broken.
    """
    if explicit:
        return explicit.strip().strip("/")
    env = os.environ.get("KB_REPO")
    if env:
        return env.strip().strip("/")
    try:
        url = subprocess.run(
            ["git", "-C", str(ROOT), "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(?:github\.com[:/])([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(1) if m else None


def edit_url(slug, path):
    return f"https://github.com/{slug}/edit/{EDIT_BRANCH}/{path}" if slug else None


def issue_url(slug, title, body):
    if not slug:
        return None
    q = urllib.parse.urlencode({"title": title, "body": body, "labels": "triage"})
    return f"https://github.com/{slug}/issues/new?{q}"


def entry_actions(e, slug, depth=0) -> str:
    """Action bar shown on every entry: GitHub links always, live editing when
    served by scripts/serve.py (which answers /api/, unlike GitHub Pages)."""
    links = []
    eu = edit_url(slug, e["path"])
    if eu:
        links.append(f'<a class="btn" href="{eu}" rel="noopener">Edit on GitHub</a>')
    iu = issue_url(
        slug,
        f"triage: {e['name']}",
        f"Entry: `{e['path']}`\n\nWhat should change and why:\n\n",
    )
    if iu:
        links.append(f'<a class="btn" href="{iu}" rel="noopener">Raise an issue</a>')
    links.append('<button class="btn local" id="edit-toggle" hidden>Edit here</button>')
    return f'<div class="actions" data-name="{html.escape(e["name"])}">' + "".join(links) + "</div>"


# --------------------------------------------------------------------------
# minimal markdown rendering (headings, lists, tables, code, inline spans)
# --------------------------------------------------------------------------

def _inline(text: str, known: set) -> str:
    out = html.escape(text)
    out = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", out)

    def wikilink(m):
        target = m.group(1)
        if target in known:
            return f'<a class="wl" href="{target}.html">{target}</a>'
        return f'<span class="wl missing" title="no entry with this name">{target}</span>'

    out = re.sub(r"\[\[([^\]]+)\]\]", wikilink, out)
    out = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?!\w)", r"<em>\1</em>", out)
    return out


def render_markdown(body: str, known: set) -> str:
    lines = body.splitlines()
    out = []
    i = 0
    para: list[str] = []

    def flush():
        if para:
            out.append("<p>" + _inline(" ".join(para), known) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            flush()
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
            continue

        if not stripped:
            flush()
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush()
            level = min(len(m.group(1)) + 1, 6)
            out.append(f"<h{level}>{_inline(m.group(2), known)}</h{level}>")
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and re.match(
            r"^\|[\s:|-]+\|$", lines[i + 1].strip()
        ):
            flush()
            header = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head = "".join(f"<th>{_inline(c, known)}</th>" for c in header)
            body_rows = "".join(
                "<tr>" + "".join(f"<td>{_inline(c, known)}</td>" for c in r) + "</tr>"
                for r in rows
            )
            out.append(
                f"<div class='tablewrap'><table><thead><tr>{head}</tr></thead>"
                f"<tbody>{body_rows}</tbody></table></div>"
            )
            continue

        if re.match(r"^[-*]\s+", stripped) or re.match(r"^\d+[.)]\s+", stripped):
            flush()
            ordered = bool(re.match(r"^\d+[.)]\s+", stripped))
            items: list[str] = []
            while i < len(lines):
                s = lines[i].strip()
                if re.match(r"^[-*]\s+", s) or re.match(r"^\d+[.)]\s+", s):
                    items.append(re.sub(r"^([-*]|\d+[.)])\s+", "", s))
                elif s and lines[i].startswith((" ", "\t")) and items:
                    items[-1] += " " + s
                else:
                    break
                i += 1
            tag = "ol" if ordered else "ul"
            lis = "".join(f"<li>{_inline(it, known)}</li>" for it in items)
            out.append(f"<{tag}>{lis}</{tag}>")
            continue

        para.append(stripped)
        i += 1

    flush()
    return "\n".join(out)


# --------------------------------------------------------------------------
# data collection
# --------------------------------------------------------------------------

def collect():
    entries = []
    for t, path in iter_entries():
        try:
            fm, body = parse_frontmatter(path)
        except OSError as e:
            print(f"warning: skipping {path}: {e}", file=sys.stderr)
            continue
        links = fm.get("links") or []
        if not isinstance(links, list):
            links = []
        entries.append(
            {
                "name": fm.get("name", path.stem),
                "type": t,
                "description": fm.get("description", ""),
                "confidence": fm.get("confidence", "unverified"),
                "created": fm.get("created", ""),
                "last_verified": fm.get("last_verified", ""),
                "source": fm.get("source", ""),
                "due": fm.get("due", ""),
                "links": links,
                "body": body.strip(),
                "path": str(path.relative_to(ROOT)),
            }
        )
    known = {e["name"] for e in entries}
    for e in entries:
        e["backlinks"] = sorted(
            o["name"] for o in entries if e["name"] in o["links"] and o["name"] != e["name"]
        )
        e["links"] = [ln for ln in e["links"] if ln in known]
    entries.sort(key=lambda e: (e["type"], e["name"]))
    return entries


def mermaid_source(entries) -> str:
    def nid(name):
        return "n_" + re.sub(r"[^a-zA-Z0-9_]", "_", name)

    lines = ["flowchart LR"]
    for t, color in TYPE_COLORS.items():
        lines.append(f"    classDef {t} fill:{color},color:#fff,stroke:none")
    for e in entries:
        lines.append(f'    {nid(e["name"])}["{e["name"]}<br/>({e["confidence"]})"]:::{e["type"]}')
    for e in entries:
        for link in e["links"]:
            lines.append(f'    {nid(e["name"])} --> {nid(link)}')
    if not entries:
        lines.append('    empty["(no entries yet)"]')
    return "\n".join(lines)


# --------------------------------------------------------------------------
# page rendering
# --------------------------------------------------------------------------

CSS = """
:root{--bg:#fbfaf8;--fg:#1d1c1a;--muted:#6a675f;--line:#e2ded6;--card:#fff;--accent:#0b6bcb}
@media (prefers-color-scheme:dark){
:root{--bg:#16171a;--fg:#e8e6e1;--muted:#9a978f;--line:#2c2e33;--card:#1d1f23;--accent:#79b8ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:60rem;margin:0 auto;padding:2rem 1.25rem 5rem}
a{color:var(--accent)}
header.top{border-bottom:1px solid var(--line);margin-bottom:1.75rem;padding-bottom:1rem}
header.top h1{margin:0 0 .25rem;font-size:1.5rem}
header.top p{margin:0;color:var(--muted)}
nav.crumbs{margin-bottom:1rem;font-size:.9rem;color:var(--muted)}
.controls{display:flex;flex-wrap:wrap;gap:.5rem;margin-bottom:1.25rem}
#q{flex:1 1 16rem;padding:.6rem .8rem;border:1px solid var(--line);border-radius:.5rem;
background:var(--card);color:var(--fg);font-size:1rem}
.chip{border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer;
border-radius:999px;padding:.35rem .8rem;font-size:.85rem}
.chip[aria-pressed=true]{background:var(--fg);color:var(--bg);border-color:var(--fg)}
.card{background:var(--card);border:1px solid var(--line);border-radius:.6rem;
padding:.9rem 1rem;margin-bottom:.7rem}
.card h3{margin:0 0 .3rem;font-size:1.05rem}
.card p{margin:0;color:var(--muted);font-size:.95rem}
.meta{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:.55rem;font-size:.75rem}
.tag{border-radius:999px;padding:.1rem .55rem;color:#fff}
.tag.conf{background:transparent;color:var(--muted);border:1px solid var(--line)}
.tag.status{font-weight:600;letter-spacing:.02em}
.legend{margin-bottom:2.5rem}
.legend th{padding-bottom:.5rem;border-bottom:1px solid var(--line)}
.legend td{padding:.5rem .75rem .5rem 0;vertical-align:top}
.legend td.num{text-align:right;padding-right:0;color:var(--muted)}
h2 .tag.status{vertical-align:middle;font-size:.6em}
.stats{display:flex;flex-wrap:wrap;gap:1.5rem;margin-bottom:1.5rem;font-size:.9rem;color:var(--muted)}
.stats b{display:block;font-size:1.5rem;color:var(--fg)}
.entry h2{margin-top:1.8rem}
.fm{width:100%;border-collapse:collapse;margin:1rem 0 1.75rem;font-size:.9rem}
.fm th{text-align:left;padding:.35rem .75rem .35rem 0;color:var(--muted);
font-weight:500;white-space:nowrap;vertical-align:top}
.fm td{padding:.35rem 0}
code{background:rgba(127,127,127,.15);padding:.1rem .35rem;border-radius:.25rem;font-size:.9em}
pre{background:var(--card);border:1px solid var(--line);border-radius:.5rem;
padding:.9rem;overflow-x:auto}
pre code{background:none;padding:0}
.tablewrap{overflow-x:auto}
.tablewrap table{border-collapse:collapse;width:100%;font-size:.92rem}
.tablewrap th,.tablewrap td{border:1px solid var(--line);padding:.4rem .6rem;text-align:left}
.wl.missing{color:var(--muted);border-bottom:1px dotted var(--muted)}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--line);
color:var(--muted);font-size:.85rem}
.empty{color:var(--muted);font-style:italic}
.actions{display:flex;flex-wrap:wrap;gap:.5rem;margin:-.5rem 0 1.5rem}
.btn{display:inline-block;border:1px solid var(--line);background:var(--card);color:var(--fg);
border-radius:.5rem;padding:.35rem .8rem;font-size:.85rem;cursor:pointer;text-decoration:none}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.editor{background:var(--card);border:1px solid var(--line);border-radius:.6rem;
padding:1rem;margin-bottom:1.75rem}
.editor label{display:block;font-size:.8rem;color:var(--muted);margin:.6rem 0 .2rem}
.editor input,.editor select,.editor textarea{width:100%;padding:.5rem;border-radius:.4rem;
border:1px solid var(--line);background:var(--bg);color:var(--fg);font:inherit;font-size:.95rem}
.editor textarea{min-height:16rem;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
font-size:.85rem}
.editor .row{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:.9rem;align-items:center}
.status{font-size:.85rem;color:var(--muted)}
.reasons{display:flex;flex-wrap:wrap;gap:.35rem;margin-top:.5rem}
.reason{border:1px solid var(--line);border-radius:999px;padding:.1rem .55rem;font-size:.75rem;
color:var(--muted)}
.sev-0 .reason,.sev-1 .reason{border-color:#ef6c00;color:#ef6c00}
"""


APP_JS = r"""
// Progressive enhancement: the generated site is read-only on GitHub Pages and
// becomes an editor when it is served by scripts/serve.py, which answers /api/.
(async function () {
  const api = window.KB_API || "api/";
  let caps = null;
  try {
    const r = await fetch(api + "capabilities", { cache: "no-store" });
    if (r.ok) caps = await r.json();
  } catch (e) { /* static host: stay read-only */ }
  if (!caps || !caps.editable) return;
  document.body.classList.add("editable");
  for (const b of document.querySelectorAll(".btn.local")) b.hidden = false;

  async function post(path, payload) {
    const r = await fetch(api + path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || r.statusText);
    return data;
  }
  window.kbPost = post;

  // --- triage page: verify in place
  for (const btn of document.querySelectorAll("[data-verify]")) {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try { await post("verify/" + encodeURIComponent(btn.dataset.verify), {}); location.reload(); }
      catch (e) { btn.disabled = false; alert(e.message); }
    });
  }

  // --- entry page: full editor
  const holder = document.getElementById("editor");
  const raw = document.getElementById("entry-data");
  const toggle = document.getElementById("edit-toggle");
  if (!holder || !raw || !toggle) return;
  const e = JSON.parse(raw.textContent);
  const opts = caps.confidence
    .map((c) => `<option${c === e.confidence ? " selected" : ""}>${c}</option>`).join("");
  holder.innerHTML = `
    <label for="f-desc">description</label>
    <input id="f-desc" value="${e.description.replace(/"/g, "&quot;")}">
    <label for="f-conf">confidence</label>
    <select id="f-conf">${opts}</select>
    <label for="f-links">links (comma separated)</label>
    <input id="f-links" value="${e.links.join(", ")}">
    <label for="f-body">body</label>
    <textarea id="f-body" spellcheck="false">${e.body.replace(/</g, "&lt;")}</textarea>
    <div class="row">
      <button class="btn" id="f-save">Save</button>
      <button class="btn" id="f-verify">Mark verified today</button>
      <button class="btn" id="f-delete">Delete</button>
      <span class="status" id="f-status"></span>
    </div>`;
  const status = holder.querySelector("#f-status");
  const say = (m) => { status.textContent = m; };

  toggle.addEventListener("click", () => {
    holder.hidden = !holder.hidden;
    toggle.textContent = holder.hidden ? "Edit here" : "Close editor";
  });
  holder.querySelector("#f-save").addEventListener("click", async () => {
    say("saving…");
    try {
      await post("entry/" + encodeURIComponent(e.name), {
        description: holder.querySelector("#f-desc").value,
        confidence: holder.querySelector("#f-conf").value,
        links: holder.querySelector("#f-links").value.split(",")
          .map((s) => s.trim()).filter(Boolean),
        body: holder.querySelector("#f-body").value,
      });
      location.reload();
    } catch (err) { say(err.message); }
  });
  holder.querySelector("#f-verify").addEventListener("click", async () => {
    say("verifying…");
    try {
      await post("verify/" + encodeURIComponent(e.name),
                 { confidence: holder.querySelector("#f-conf").value });
      location.reload();
    } catch (err) { say(err.message); }
  });
  holder.querySelector("#f-delete").addEventListener("click", async () => {
    if (!confirm(`Delete ${e.name}? Inbound links are stripped too.`)) return;
    try {
      await post("delete/" + encodeURIComponent(e.name), { force: true });
      location.href = (window.KB_API || "api/").replace(/api\/$/, "") + "index.html";
    } catch (err) { say(err.message); }
  });
})();
"""


def page(title: str, body: str, depth: int = 0, extra_head: str = "") -> str:
    up = "../" * depth
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{up}style.css">
{extra_head}
</head>
<body>
<div class="wrap">
{body}
<footer>Generated by <code>scripts/build_site.py</code> from
<code>memory/</code> on {date.today().isoformat()}.
Structured data: <a href="{up}data.json">data.json</a>.</footer>
</div>
<script>window.KB_API={json.dumps(up + "api/")};</script>
<script src="{up}app.js"></script>
</body>
</html>
"""


def tag(t: str) -> str:
    return f'<span class="tag" style="background:{TYPE_COLORS.get(t, "#555")}">{t}</span>'


def status_tag(key: str) -> str:
    s = STATUS_BY_KEY[key]
    return (
        f'<span class="tag status" style="background:{STATUS_COLORS.get(key, "#555")}" '
        f'title="{html.escape(s["meaning"])}">{html.escape(s["label"].lower())}</span>'
    )


def card(e, depth=0) -> str:
    up = "../" * depth
    status = e.get("status", "current")
    return (
        f'<article class="card" data-type="{e["type"]}" data-status="{status}" '
        f'data-hay="{html.escape(e["hay"])}">'
        f'<h3><a href="{up}entry/{e["name"]}.html">{html.escape(e["name"])}</a></h3>'
        f'<p>{html.escape(e["description"])}</p>'
        f'<div class="meta">{tag(e["type"])}{status_tag(status)}'
        f'<span class="tag conf">{html.escape(e["confidence"])}</span>'
        f'<span class="tag conf">{html.escape(e["created"])}</span></div>'
        "</article>"
    )


def build_status(entries, statuses, slug=None) -> str:
    """The status board: where every entry stands and what moves it.

    Triage lists only what is wrong. This lists everything, grouped by the
    one status that applies, with the exact command that changes it — the
    same model `kb.py status` prints.
    """
    by_name = {e["name"]: e for e in entries}
    counts = {k: sum(1 for r in statuses if r["status"] == k) for k in STATUS_ORDER}

    legend = "".join(
        f'<tr><td>{status_tag(s["key"])}</td><td>{html.escape(s["meaning"])}</td>'
        f'<td><code>{html.escape(s["action"])}</code></td>'
        f'<td class="num">{counts[s["key"]]}</td></tr>'
        for s in STATUS_MODEL
    )

    sections = []
    for key in STATUS_ORDER:
        rows = [r for r in statuses if r["status"] == key]
        if not rows:
            continue
        s = STATUS_BY_KEY[key]
        items = []
        for r in rows:
            e = by_name.get(r["name"], {})
            when = (
                f'verified {r["age_days"]}d ago, review by {html.escape(r["review_by"])}'
                if r["age_days"] is not None
                else "never verified"
            )
            items.append(
                f'<article class="card">'
                f'<h3><a href="entry/{r["name"]}.html">{html.escape(r["name"])}</a></h3>'
                f'<p>{html.escape(e.get("description", r["description"]))}</p>'
                f'<div class="meta">{tag(r["type"])}'
                f'<span class="tag conf">{html.escape(r["confidence"])}</span>'
                f'<span class="tag conf">{when}</span></div>'
                f'<div class="reasons"><code>{html.escape(r["action"])}</code></div>'
                "</article>"
            )
        sections.append(
            f'<h2>{status_tag(key)} {html.escape(s["label"])} '
            f"<span class='empty'>({len(rows)})</span></h2>"
            f"<p>{html.escape(s['meaning'])} "
            f"To change it: <code>{html.escape(s['action'])}</code></p>"
            + "".join(items)
        )

    body = (
        '<nav class="crumbs"><a href="index.html">← all memory</a></nav>'
        '<header class="top"><h1>Status</h1>'
        f"<p>Every entry sits in exactly one status. "
        f"{counts['current']} of {len(statuses)} are current.</p></header>"
        "<p>An entry that qualifies for several statuses shows the most urgent one, "
        "so the action below is always the single next thing to do about it. "
        "Run <code>python3 scripts/kb.py status</code> for the same board in the "
        "terminal, or <code>python3 scripts/serve.py</code> to act on it in place.</p>"
        f'<table class="fm legend"><thead><tr><th>Status</th><th>What it means</th>'
        f"<th>How to change it</th><th>Now</th></tr></thead><tbody>{legend}</tbody></table>"
        + "".join(sections)
    )
    return page("Status", body)


def build_index(entries, triage=(), statuses=(), slug=None) -> str:
    triage_count = len(triage)
    current = sum(1 for r in statuses if r["status"] == "current")
    by_type = {t: [e for e in entries if e["type"] == t] for t in TYPES}
    chips = "".join(
        f'<button class="chip" data-filter="{t}" aria-pressed="false">{t} ({len(by_type[t])})</button>'
        for t in TYPES
        if by_type[t]
    )
    conf = {c: sum(1 for e in entries if e["confidence"] == c) for c in CONFIDENCE_ORDER}
    link_count = sum(len(e["links"]) for e in entries)
    newest = max((e["created"] for e in entries if e["created"]), default="—")

    body = f"""<header class="top">
<h1>Agent memory</h1>
<p>Everything this knowledge base remembers, browsable by type, link, and text.</p>
</header>
<div class="stats">
<div><b>{len(entries)}</b> entries</div>
<div><b>{len([t for t in TYPES if by_type[t]])}</b> types in use</div>
<div><b>{link_count}</b> links</div>
<div><b>{html.escape(newest)}</b> newest</div>
<div><b>{conf['verified'] + conf['high']}</b> verified or high confidence</div>
<div><b>{current}/{len(statuses)}</b> current</div>
</div>
<p><a href="status.html">Status board</a> · <a href="graph.html">Memory graph</a>
 · <a href="types.html">Memory types</a>
 · <a href="triage.html">Triage ({triage_count})</a> · <a href="data.json">Raw data</a></p>
<div class="controls">
<input id="q" type="search" placeholder="Search names, descriptions, and bodies…"
 autocomplete="off">
<button class="chip" data-filter="" aria-pressed="true">all</button>
{chips}
</div>
<div id="results">
{"".join(card(e) for e in entries) or '<p class="empty">No entries yet.</p>'}
</div>
<p id="none" class="empty" hidden>Nothing matches that.</p>
<script>
const cards=[...document.querySelectorAll('.card')];
const chips=[...document.querySelectorAll('.chip')];
const q=document.getElementById('q');
let type='';
function apply(){{
  const needle=q.value.trim().toLowerCase();
  let shown=0;
  for(const c of cards){{
    const ok=(!type||c.dataset.type===type)&&(!needle||c.dataset.hay.includes(needle));
    c.hidden=!ok; if(ok) shown++;
  }}
  document.getElementById('none').hidden=shown>0;
}}
q.addEventListener('input',apply);
for(const c of chips) c.addEventListener('click',()=>{{
  type=c.dataset.filter;
  for(const o of chips) o.setAttribute('aria-pressed',String(o===c));
  apply();
}});
</script>
"""
    return page("Agent memory", body)


def build_types(entries) -> str:
    parts = ['<nav class="crumbs"><a href="index.html">← all memory</a></nav>',
             '<header class="top"><h1>Memory types</h1>'
             '<p>The taxonomy this knowledge base stores against.</p></header>']
    for t in TYPES:
        items = [e for e in entries if e["type"] == t]
        parts.append(f"<h2>{tag(t)} {t} <span class='empty'>({len(items)})</span></h2>")
        parts.append(f"<p>{html.escape(TYPE_BLURB.get(t, ''))}</p>")
        if items:
            parts.append(
                "<ul>"
                + "".join(
                    f'<li><a href="entry/{e["name"]}.html">{html.escape(e["name"])}</a> — '
                    f'{html.escape(e["description"])}</li>'
                    for e in items
                )
                + "</ul>"
            )
        else:
            parts.append('<p class="empty">No entries of this type yet.</p>')
    return page("Memory types", "\n".join(parts))


def build_graph(entries) -> str:
    src = mermaid_source(entries)
    head = (
        '<script type="module">'
        'import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";'
        'mermaid.initialize({startOnLoad:true,securityLevel:"loose"});'
        "</script>"
    )
    body = (
        '<nav class="crumbs"><a href="index.html">← all memory</a></nav>'
        '<header class="top"><h1>Memory graph</h1>'
        "<p>Entries as nodes, <code>links:</code> as edges, coloured by type.</p></header>"
        f'<div class="tablewrap"><pre class="mermaid">{html.escape(src)}</pre></div>'
        f'<details><summary>Mermaid source</summary><pre><code>{html.escape(src)}</code></pre></details>'
    )
    return page("Memory graph", body, extra_head=head)


def build_triage(entries, triage, slug=None) -> str:
    """Human-facing queue: what needs attention, most urgent first.

    Same data the `kb.py triage` command prints, so the site and the CLI can
    never disagree about what is outstanding.
    """
    by_name = {e["name"]: e for e in entries}
    cards = []
    for rec in triage:
        e = by_name.get(rec["name"], {})
        reasons = "".join(
            f'<span class="reason" title="{html.escape(r["detail"])}">'
            f'{TRIAGE_BLURB.get(r["code"], r["code"])}</span>'
            for r in rec["reasons"]
        )
        actions = []
        eu = edit_url(slug, rec["path"])
        if eu:
            actions.append(f'<a class="btn" href="{eu}" rel="noopener">Edit on GitHub</a>')
        iu = issue_url(
            slug,
            f"triage: {rec['name']}",
            "Flagged by `kb.py triage` for: "
            + ", ".join(r["code"] for r in rec["reasons"])
            + f"\n\nEntry: `{rec['path']}`\n\n",
        )
        if iu:
            actions.append(f'<a class="btn" href="{iu}" rel="noopener">Raise an issue</a>')
        actions.append(
            f'<button class="btn local" data-verify="{html.escape(rec["name"])}" hidden>'
            "Mark verified</button>"
        )
        cards.append(
            f'<article class="card sev-{rec["severity"]}">'
            f'<h3><a href="entry/{rec["name"]}.html">{html.escape(rec["name"])}</a></h3>'
            f'<p>{html.escape(e.get("description", rec.get("description", "")))}</p>'
            f'<div class="meta">{tag(rec["type"])}'
            f'<span class="tag conf">{html.escape(rec["confidence"])}</span></div>'
            f'<div class="reasons">{reasons}</div>'
            f'<div class="actions">{"".join(actions)}</div>'
            "</article>"
        )

    intro = (
        "<p>Every entry the linter would warn about, most urgent first. "
        "Editing links go to GitHub's own editor; run "
        "<code>python3 scripts/serve.py</code> to edit and verify in place.</p>"
    )
    body = (
        '<nav class="crumbs"><a href="index.html">← all memory</a></nav>'
        '<header class="top"><h1>Triage</h1>'
        f"<p>{len(triage)} of {len(entries)} entries need attention.</p></header>"
        + intro
        + ("".join(cards) or '<p class="empty">Nothing needs attention.</p>')
    )
    return page("Triage", body)


def build_entry(e, entries, slug=None) -> str:
    known = {o["name"] for o in entries}
    rows = [("type", tag(e["type"])), ("confidence", html.escape(e["confidence"]))]
    if e.get("status"):
        s = STATUS_BY_KEY[e["status"]]
        rows.append(
            (
                "status",
                f'{status_tag(e["status"])} {html.escape(s["meaning"])}<br>'
                f'To change it: <code>{html.escape(e.get("action", s["action"]))}</code>',
            )
        )
    for key in ("created", "last_verified", "due", "source"):
        if e.get(key):
            rows.append((key.replace("_", " "), html.escape(e[key])))
    if e.get("review_by"):
        rows.append(("review by", html.escape(e["review_by"])))
    rows.append(("file", f'<code>{html.escape(e["path"])}</code>'))
    fm = "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows)

    def linklist(names):
        if not names:
            return '<p class="empty">None.</p>'
        return (
            "<ul>"
            + "".join(f'<li><a href="{n}.html">{html.escape(n)}</a></li>' for n in names)
            + "</ul>"
        )

    payload = json.dumps(
        {k: e[k] for k in ("name", "type", "description", "confidence", "links", "body")}
    )
    body = f"""<nav class="crumbs"><a href="../index.html">← all memory</a></nav>
<header class="top"><h1>{html.escape(e["name"])}</h1>
<p>{html.escape(e["description"])}</p></header>
{entry_actions(e, slug, depth=1)}
<div class="editor" id="editor" hidden></div>
<script type="application/json" id="entry-data">{payload}</script>
<table class="fm">{fm}</table>
<div class="entry">{render_markdown(e["body"], known)}</div>
<h2>Links out</h2>{linklist(e["links"])}
<h2>Linked from</h2>{linklist(e["backlinks"])}
"""
    return page(e["name"], body, depth=1)


def build(out_dir: pathlib.Path, slug=None) -> int:
    entries = collect()
    triage = triage_report()
    statuses = status_report()
    by_name = {r["name"]: r for r in statuses}
    for e in entries:
        r = by_name.get(e["name"])
        if r:
            e["status"] = r["status"]
            e["action"] = r["action"]
            e["review_by"] = r["review_by"]
        e["hay"] = " ".join(
            [e["name"], e["description"], e["type"], e["confidence"], e["body"]]
        ).lower()

    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "entry").mkdir(parents=True, exist_ok=True)

    (out_dir / "style.css").write_text(CSS.strip() + "\n", encoding="utf-8")
    (out_dir / "app.js").write_text(APP_JS.strip() + "\n", encoding="utf-8")
    (out_dir / "index.html").write_text(
        build_index(entries, triage, statuses, slug), encoding="utf-8"
    )
    (out_dir / "types.html").write_text(build_types(entries), encoding="utf-8")
    (out_dir / "graph.html").write_text(build_graph(entries), encoding="utf-8")
    (out_dir / "triage.html").write_text(build_triage(entries, triage, slug), encoding="utf-8")
    (out_dir / "status.html").write_text(
        build_status(entries, statuses, slug), encoding="utf-8"
    )
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    payload = [{k: v for k, v in e.items() if k != "hay"} for e in entries]
    (out_dir / "data.json").write_text(
        json.dumps(
            {
                "generated": date.today().isoformat(),
                "count": len(payload),
                "repo": slug,
                "triage": triage,
                "status_model": STATUS_MODEL,
                "status": statuses,
                "entries": payload,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    for e in entries:
        (out_dir / "entry" / f"{e['name']}.html").write_text(
            build_entry(e, entries, slug), encoding="utf-8"
        )

    return len(entries)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render memory/ into a static site.")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output directory (default: site/)")
    ap.add_argument(
        "--repo",
        help="owner/name for GitHub edit links (default: $KB_REPO, else the origin remote)",
    )
    args = ap.parse_args(argv)
    out = pathlib.Path(args.out)
    count = build(out, repo_slug(args.repo))
    print(f"wrote {out} ({count} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
