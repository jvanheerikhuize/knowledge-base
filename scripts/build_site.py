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
import pathlib
import re
import shutil
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from kb import ROOT, TYPES, iter_entries, parse_frontmatter  # noqa: E402

DEFAULT_OUT = ROOT / "site"

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
</body>
</html>
"""


def tag(t: str) -> str:
    return f'<span class="tag" style="background:{TYPE_COLORS.get(t, "#555")}">{t}</span>'


def card(e, depth=0) -> str:
    up = "../" * depth
    return (
        f'<article class="card" data-type="{e["type"]}" data-hay="{html.escape(e["hay"])}">'
        f'<h3><a href="{up}entry/{e["name"]}.html">{html.escape(e["name"])}</a></h3>'
        f'<p>{html.escape(e["description"])}</p>'
        f'<div class="meta">{tag(e["type"])}'
        f'<span class="tag conf">{html.escape(e["confidence"])}</span>'
        f'<span class="tag conf">{html.escape(e["created"])}</span></div>'
        "</article>"
    )


def build_index(entries) -> str:
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
</div>
<p><a href="graph.html">Memory graph</a> · <a href="types.html">Memory types</a>
 · <a href="data.json">Raw data</a></p>
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


def build_entry(e, entries) -> str:
    known = {o["name"] for o in entries}
    rows = [("type", tag(e["type"])), ("confidence", html.escape(e["confidence"]))]
    for key in ("created", "last_verified", "due", "source"):
        if e.get(key):
            rows.append((key.replace("_", " "), html.escape(e[key])))
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

    body = f"""<nav class="crumbs"><a href="../index.html">← all memory</a></nav>
<header class="top"><h1>{html.escape(e["name"])}</h1>
<p>{html.escape(e["description"])}</p></header>
<table class="fm">{fm}</table>
<div class="entry">{render_markdown(e["body"], known)}</div>
<h2>Links out</h2>{linklist(e["links"])}
<h2>Linked from</h2>{linklist(e["backlinks"])}
"""
    return page(e["name"], body, depth=1)


def build(out_dir: pathlib.Path) -> int:
    entries = collect()
    for e in entries:
        e["hay"] = " ".join(
            [e["name"], e["description"], e["type"], e["confidence"], e["body"]]
        ).lower()

    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "entry").mkdir(parents=True, exist_ok=True)

    (out_dir / "style.css").write_text(CSS.strip() + "\n", encoding="utf-8")
    (out_dir / "index.html").write_text(build_index(entries), encoding="utf-8")
    (out_dir / "types.html").write_text(build_types(entries), encoding="utf-8")
    (out_dir / "graph.html").write_text(build_graph(entries), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    payload = [{k: v for k, v in e.items() if k != "hay"} for e in entries]
    (out_dir / "data.json").write_text(
        json.dumps(
            {"generated": date.today().isoformat(), "count": len(payload), "entries": payload},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    for e in entries:
        (out_dir / "entry" / f"{e['name']}.html").write_text(
            build_entry(e, entries), encoding="utf-8"
        )

    return len(entries)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render memory/ into a static site.")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output directory (default: site/)")
    args = ap.parse_args(argv)
    out = pathlib.Path(args.out)
    count = build(out)
    print(f"wrote {out} ({count} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
