#!/usr/bin/env python3
"""Visualization layer: regenerates memory/_generated/graph.mmd (Mermaid).

Nodes are colored by memory type; a subtle marker denotes confidence.
Edges come from each entry's `links:` frontmatter field.
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from kb import MEMORY, TYPES, iter_entries, parse_frontmatter  # noqa: E402

OUT = MEMORY / "_generated" / "graph.mmd"

TYPE_CLASS = {
    "semantic": "semantic",
    "episodic": "episodic",
    "procedural": "procedural",
    "working": "working",
    "retrieval": "retrieval",
    "parametric": "parametric",
    "prospective": "prospective",
}

CLASS_DEFS = """
    classDef semantic fill:#2e7d32,color:#fff
    classDef episodic fill:#1565c0,color:#fff
    classDef procedural fill:#6a1b9a,color:#fff
    classDef working fill:#8d6e63,color:#fff
    classDef retrieval fill:#00838f,color:#fff
    classDef parametric fill:#455a64,color:#fff
    classDef prospective fill:#ef6c00,color:#fff
""".strip("\n")


def node_id(name: str) -> str:
    return "n_" + re.sub(r"[^a-zA-Z0-9_]", "_", name)


def main():
    entries = list(iter_entries())
    lines = ["flowchart LR", CLASS_DEFS]

    names = set()
    node_lines = []
    edge_lines = []

    for t, path in entries:
        fm, _ = parse_frontmatter(path)
        name = fm.get("name", path.stem)
        names.add(name)
        conf = fm.get("confidence", "unverified")
        label = f"{name}\\n({conf})"
        node_lines.append(f'    {node_id(name)}["{label}"]:::{TYPE_CLASS[t]}')

    for t, path in entries:
        fm, _ = parse_frontmatter(path)
        name = fm.get("name", path.stem)
        for link in fm.get("links", []) or []:
            if link in names:
                edge_lines.append(f"    {node_id(name)} --> {node_id(link)}")

    lines.extend(node_lines)
    lines.extend(edge_lines)

    if not entries:
        lines.append('    empty["(no entries yet — run kb.py new)"]')

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} ({len(entries)} entries, {len(edge_lines)} links)")


if __name__ == "__main__":
    main()
