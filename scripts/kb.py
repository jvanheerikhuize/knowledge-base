#!/usr/bin/env python3
"""Interface layer for the file-based agent memory knowledge base.

No third-party dependencies — stdlib only, so the KB stays infra-free.
Run `kb.py --help` for usage.
"""
import argparse
import datetime
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG_FILE = pathlib.Path(__file__).resolve().parent / ".kb-config"


def _memory_dir_name() -> str:
    if CONFIG_FILE.is_file():
        name = CONFIG_FILE.read_text().strip()
        if name:
            return name
    return "memory"


MEMORY = ROOT / _memory_dir_name()
TYPES = ["semantic", "episodic", "procedural", "working", "retrieval", "parametric", "prospective"]
TEMPLATE = MEMORY / "templates" / "entry.template.md"
SCHEMA_FILE = MEMORY / "schema" / "entry.schema.json"
STALE_DAYS = 90
UNVERIFIED_DAYS = 30


def _load_schema():
    if SCHEMA_FILE.is_file():
        return json.loads(SCHEMA_FILE.read_text())
    return None


def iter_entries():
    for t in TYPES:
        folder = MEMORY / t
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            if path.name == "README.md" or path.name.endswith(".template.md"):
                continue
            yield t, path


def parse_frontmatter(path: pathlib.Path):
    text = path.read_text()
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm_text, body = m.group(1), m.group(2)
    fm = {}
    for line in fm_text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1].strip()
            fm[key] = [v.strip() for v in inner.split(",") if v.strip()] if inner else []
        else:
            fm[key] = value
    return fm, body


def cmd_list(args):
    found = False
    for t, path in iter_entries():
        if args.type and t != args.type:
            continue
        fm, _ = parse_frontmatter(path)
        found = True
        print(f"[{t:11}] {fm.get('name', path.stem):30} conf={fm.get('confidence', '?'):10} {fm.get('description', '')}")
    if not found:
        print("(no entries yet)")


def cmd_search(args):
    query = args.query.lower()
    hits = 0
    for t, path in iter_entries():
        fm, body = parse_frontmatter(path)
        haystack = (path.read_text()).lower()
        if query in haystack:
            hits += 1
            print(f"[{t}] {fm.get('name', path.stem)} — {fm.get('description', '')}\n  {path.relative_to(ROOT)}")
    if not hits:
        print("(no matches)")


def cmd_show(args):
    for t, path in iter_entries():
        fm, _ = parse_frontmatter(path)
        if fm.get("name") == args.name or path.stem == args.name:
            print(path.read_text())
            return
    print(f"no entry named '{args.name}'", file=sys.stderr)
    sys.exit(1)


def cmd_new(args):
    if args.type not in TYPES:
        print(f"type must be one of: {', '.join(TYPES)}", file=sys.stderr)
        sys.exit(1)
    slug = re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")
    folder = MEMORY / args.type
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{slug}.md"
    if dest.exists():
        print(f"entry already exists: {dest.relative_to(ROOT)}", file=sys.stderr)
        sys.exit(1)
    today = datetime.date.today().isoformat()
    text = TEMPLATE.read_text()
    text = text.replace("REPLACE-ME-kebab-case-slug", slug)
    text = text.replace("type: semantic", f"type: {args.type}")
    text = text.replace("created: 1970-01-01", f"created: {today}")
    text = text.replace("last_verified: 1970-01-01", f"last_verified: {today}")
    dest.write_text(text)
    print(f"created {dest.relative_to(ROOT)}")


def cmd_lint(args):
    problems = []  # always fatal
    warnings = []  # fatal only with --strict
    seen_names = {}
    today = datetime.date.today()

    schema = _load_schema()
    required_fields = schema.get("required", []) if schema else []
    name_pattern = None
    type_enum = None
    if schema:
        name_pattern = schema.get("properties", {}).get("name", {}).get("pattern")
        type_enum = schema.get("properties", {}).get("type", {}).get("enum")

    for t, path in iter_entries():
        fm, _ = parse_frontmatter(path)
        name = fm.get("name", path.stem)
        rel = path.relative_to(ROOT)

        if name in seen_names:
            problems.append(f"duplicate slug '{name}': {seen_names[name]} vs {rel}")
        else:
            seen_names[name] = rel

        confidence = fm.get("confidence")
        if confidence not in {"verified", "high", "medium", "low", "unverified"}:
            problems.append(f"{rel}: missing/invalid confidence field")

        for field in required_fields:
            if not fm.get(field):
                problems.append(f"{rel}: missing required field '{field}' (see memory/schema/entry.schema.json)")

        raw_name = fm.get("name")
        if raw_name and name_pattern and not re.match(name_pattern, raw_name):
            problems.append(f"{rel}: name '{raw_name}' does not match required pattern {name_pattern}")

        entry_type = fm.get("type")
        if entry_type and type_enum and entry_type not in type_enum:
            problems.append(f"{rel}: type '{entry_type}' is not one of {type_enum}")

        created = fm.get("created")
        if created:
            try:
                datetime.date.fromisoformat(created)
            except ValueError:
                problems.append(f"{rel}: created is not a valid date: {created!r}")

        lv = fm.get("last_verified")
        if lv:
            try:
                lv_date = datetime.date.fromisoformat(lv)
                age = (today - lv_date).days
                if age > STALE_DAYS:
                    warnings.append(f"{rel}: stale, last_verified {age}d ago (>{STALE_DAYS}d)")
                if confidence == "unverified" and age > UNVERIFIED_DAYS:
                    warnings.append(f"{rel}: unverified for {age}d (>{UNVERIFIED_DAYS}d) — verify or discard")
            except ValueError:
                problems.append(f"{rel}: last_verified is not a valid date: {lv!r}")

    # second pass for dangling links, now that we know all names
    for t, path in iter_entries():
        fm, _ = parse_frontmatter(path)
        for link in fm.get("links", []) or []:
            if link not in seen_names:
                problems.append(f"{path.relative_to(ROOT)}: dangling link '{link}'")

    if not problems and not warnings:
        print("lint clean — no issues found")
        return

    for p in problems:
        print(f"- {p}")
    for w in warnings:
        print(f"- [warning] {w}")

    total = len(problems) + len(warnings)
    print(f"\n{total} issue(s) found ({len(problems)} error(s), {len(warnings)} warning(s))")

    if problems or (args.strict and warnings):
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list entries")
    p_list.add_argument("--type", choices=TYPES)
    p_list.set_defaults(func=cmd_list)

    p_search = sub.add_parser("search", help="keyword search across all entries")
    p_search.add_argument("query")
    p_search.set_defaults(func=cmd_search)

    p_show = sub.add_parser("show", help="print one entry")
    p_show.add_argument("name")
    p_show.set_defaults(func=cmd_show)

    p_new = sub.add_parser("new", help="scaffold a new entry")
    p_new.add_argument("name")
    p_new.add_argument("--type", required=True, choices=TYPES)
    p_new.set_defaults(func=cmd_new)

    p_lint = sub.add_parser("lint", help="schema, duplicate-slug, dangling-link, and staleness checks")
    p_lint.add_argument("--strict", action="store_true",
                         help="treat staleness/unverified-age warnings as fatal")
    p_lint.set_defaults(func=cmd_lint)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
