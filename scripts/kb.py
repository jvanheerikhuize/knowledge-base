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
        try:
            name = CONFIG_FILE.read_text(encoding="utf-8").strip()
        except OSError as e:
            print(f"error: could not read {CONFIG_FILE}: {e}", file=sys.stderr)
            sys.exit(2)
        if name:
            if "/" in name or "\\" in name or name in (".", "..") or pathlib.Path(name).is_absolute():
                print(
                    f"error: .kb-config must be a plain directory name, not a path: {name!r}",
                    file=sys.stderr,
                )
                sys.exit(2)
            return name
    return "memory"


MEMORY = ROOT / _memory_dir_name()
# Tooling machinery lives in a fixed .kb/ dir, decoupled from the (renamable)
# human-readable memory dir so the two never get tangled.
KB_DIR = ROOT / ".kb"
TYPES = ["semantic", "episodic", "procedural", "working", "retrieval", "parametric", "prospective"]
TEMPLATE = KB_DIR / "templates" / "entry.template.md"
SCHEMA_FILE = KB_DIR / "schema" / "entry.schema.json"
LOG_FILE = KB_DIR / "log.md"
STALE_DAYS = 90
UNVERIFIED_DAYS = 30
CONFIDENCE_LEVELS = ["verified", "high", "medium", "low", "unverified"]
# Lower number = more urgent; drives the order of the triage queue.
TRIAGE_SEVERITY = {
    "invalid-due": 0,
    "invalid-date": 0,
    "overdue": 1,
    "stale": 2,
    "unverified": 3,
    "never-verified": 4,
    "orphan": 5,
    "unlinked": 6,
}


def _load_schema():
    if not SCHEMA_FILE.is_file():
        return None
    try:
        return json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: could not load schema {SCHEMA_FILE}: {e}", file=sys.stderr)
        sys.exit(2)


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
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise OSError(f"not valid UTF-8: {e}") from e
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


def serialize_value(value):
    """Render a frontmatter value the way the rest of the KB writes it."""
    if isinstance(value, list):
        return "[" + ", ".join(value) + "]"
    return str(value)


def write_frontmatter(path: pathlib.Path, changes: dict):
    """Set frontmatter keys in place, preserving field order and the body.

    Existing keys are rewritten where they stand; new keys are appended to the
    end of the block. A key set to None is removed. Rewriting lines rather than
    re-serializing the whole block keeps hand-written formatting intact.
    """
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        raise ValueError(f"{path} has no frontmatter block")
    lines = m.group(1).splitlines()
    body = m.group(2)

    remaining = dict(changes)
    out = []
    for line in lines:
        key = line.partition(":")[0].strip() if ":" in line else None
        if key in remaining:
            value = remaining.pop(key)
            if value is not None:
                out.append(f"{key}: {serialize_value(value)}")
            # value is None -> drop the line
        else:
            out.append(line)
    for key, value in remaining.items():
        if value is not None:
            out.append(f"{key}: {serialize_value(value)}")

    path.write_text("---\n" + "\n".join(out) + "\n---\n" + body, encoding="utf-8")


def write_body(path: pathlib.Path, body: str):
    """Replace an entry's body, leaving its frontmatter block untouched."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        raise ValueError(f"{path} has no frontmatter block")
    body = body.strip()
    path.write_text(f"---\n{m.group(1)}\n---\n\n{body}\n" if body else f"---\n{m.group(1)}\n---\n",
                    encoding="utf-8")


def resolve(name):
    """Find one entry by frontmatter name or filename stem."""
    for t, path in iter_entries():
        try:
            fm, body = parse_frontmatter(path)
        except OSError:
            continue
        if fm.get("name") == name or path.stem == name:
            return t, path, fm, body
    return None


def _require(name):
    hit = resolve(name)
    if hit is None:
        print(f"no entry named '{name}'", file=sys.stderr)
        sys.exit(1)
    return hit


def triage_report():
    """Entries needing human attention, worst first.

    Same rules the linter warns on, but returned as data so the CLI, the site
    build, and the local edit server all present one consistent queue.
    """
    today = datetime.date.today()
    entries = []
    inbound = set()
    for t, path in iter_entries():
        try:
            fm, _ = parse_frontmatter(path)
        except OSError:
            continue
        for link in fm.get("links") or []:
            inbound.add(link)
        entries.append((t, path, fm))

    report = []
    for t, path, fm in entries:
        name = fm.get("name", path.stem)
        confidence = fm.get("confidence", "")
        reasons = []

        due = fm.get("due")
        if t == "prospective" and due:
            try:
                if datetime.date.fromisoformat(due) < today:
                    reasons.append(("overdue", f"due {due} has passed"))
            except ValueError:
                reasons.append(("invalid-due", f"unparseable due date {due!r}"))

        lv = fm.get("last_verified")
        if lv:
            try:
                age = (today - datetime.date.fromisoformat(lv)).days
                if age > STALE_DAYS:
                    reasons.append(("stale", f"last verified {age}d ago (>{STALE_DAYS}d)"))
                if confidence == "unverified" and age > UNVERIFIED_DAYS:
                    reasons.append(("unverified", f"unverified for {age}d (>{UNVERIFIED_DAYS}d)"))
            except ValueError:
                reasons.append(("invalid-date", f"unparseable last_verified {lv!r}"))
        else:
            reasons.append(("never-verified", "no last_verified date"))

        if name not in inbound:
            reasons.append(("orphan", "no other entry links to it"))
        if not (fm.get("links") or []):
            reasons.append(("unlinked", "links out to nothing"))

        if reasons:
            severity = min(TRIAGE_SEVERITY.get(code, 99) for code, _ in reasons)
            report.append({
                "name": name,
                "type": t,
                "path": str(path.relative_to(ROOT)),
                "confidence": confidence,
                "description": fm.get("description", ""),
                "severity": severity,
                "reasons": [{"code": c, "detail": d} for c, d in reasons],
            })

    report.sort(key=lambda r: (r["severity"], r["type"], r["name"]))
    return report


def cmd_triage(args):
    report = triage_report()
    if args.type:
        report = [r for r in report if r["type"] == args.type]
    if args.reason:
        report = [r for r in report
                  if any(x["code"] == args.reason for x in r["reasons"])]
    if args.json:
        print(json.dumps(report, indent=2))
        return
    if not report:
        print("triage clean — nothing needs attention")
        return
    for r in report:
        codes = ", ".join(x["code"] for x in r["reasons"])
        print(f"[{r['type']:11}] {r['name']:30} {codes}")
        for x in r["reasons"]:
            print(f"    - {x['code']}: {x['detail']}")
    print(f"\n{len(report)} entr(ies) need attention")


def cmd_verify(args):
    t, path, fm, _ = _require(args.name)
    today = datetime.date.today().isoformat()
    changes = {"last_verified": today}
    if args.confidence:
        changes["confidence"] = args.confidence
    write_frontmatter(path, changes)
    conf = args.confidence or fm.get("confidence", "?")
    _append_log(t, path.stem, today, "verified", f"confidence={conf}")
    print(f"verified {path.relative_to(ROOT)} (last_verified={today}, confidence={conf})")


def cmd_set(args):
    t, path, _, _ = _require(args.name)
    if args.field in ("name", "type"):
        print(f"refusing to change '{args.field}' — it defines the entry's identity "
              f"and its file location; create a new entry instead", file=sys.stderr)
        sys.exit(1)
    if args.field in ("created", "last_verified", "due"):
        try:
            datetime.date.fromisoformat(args.value)
        except ValueError:
            print(f"{args.field} must be an ISO date, got {args.value!r}", file=sys.stderr)
            sys.exit(1)
    if args.field == "confidence" and args.value not in CONFIDENCE_LEVELS:
        print(f"confidence must be one of: {', '.join(CONFIDENCE_LEVELS)}", file=sys.stderr)
        sys.exit(1)
    write_frontmatter(path, {args.field: args.value})
    _append_log(t, path.stem, datetime.date.today().isoformat(), "updated",
                f"{args.field}={args.value}")
    print(f"set {args.field}={args.value} on {path.relative_to(ROOT)}")


def cmd_link(args):
    t, path, fm, _ = _require(args.name)
    if resolve(args.target) is None:
        print(f"no entry named '{args.target}' — refusing to create a dangling link",
              file=sys.stderr)
        sys.exit(1)
    links = list(fm.get("links") or [])
    if args.remove:
        if args.target not in links:
            print(f"{args.name} does not link to {args.target}", file=sys.stderr)
            sys.exit(1)
        links.remove(args.target)
        verb = "unlinked"
    else:
        if args.target in links:
            print(f"{args.name} already links to {args.target}")
            return
        if args.target == fm.get("name", path.stem):
            print("an entry cannot link to itself", file=sys.stderr)
            sys.exit(1)
        links.append(args.target)
        verb = "linked"
    write_frontmatter(path, {"links": links})
    _append_log(t, path.stem, datetime.date.today().isoformat(), verb,
                f"-> {args.target}")
    print(f"{verb} {args.name} -> {args.target}")


def cmd_edit(args):
    import os
    import subprocess
    _, path, _, _ = _require(args.name)
    editor = args.editor or os.environ.get("KB_EDITOR") or os.environ.get("EDITOR")
    if not editor:
        print(f"no editor set — export EDITOR, or open {path.relative_to(ROOT)} yourself",
              file=sys.stderr)
        sys.exit(1)
    raise SystemExit(subprocess.call([*editor.split(), str(path)]))


def cmd_rm(args):
    t, path, fm, _ = _require(args.name)
    name = fm.get("name", path.stem)
    referrers = []
    for t, other in iter_entries():
        if other == path:
            continue
        try:
            other_fm, _ = parse_frontmatter(other)
        except OSError:
            continue
        if name in (other_fm.get("links") or []):
            referrers.append(other)
    if referrers and not args.force:
        print(f"refusing to delete '{name}' — still linked from:", file=sys.stderr)
        for r in referrers:
            print(f"  {r.relative_to(ROOT)}", file=sys.stderr)
        print("re-run with --force to delete and strip those links", file=sys.stderr)
        sys.exit(1)
    for r in referrers:
        r_fm, _ = parse_frontmatter(r)
        write_frontmatter(r, {"links": [x for x in r_fm.get("links") or [] if x != name]})
        print(f"unlinked {r.relative_to(ROOT)}")
    path.unlink()
    _append_log(t, path.stem, datetime.date.today().isoformat(), "deleted")
    print(f"deleted {path.relative_to(ROOT)}")


def cmd_list(args):
    found = False
    for t, path in iter_entries():
        if args.type and t != args.type:
            continue
        try:
            fm, _ = parse_frontmatter(path)
        except OSError as e:
            print(f"warning: skipping {path.relative_to(ROOT)}: {e}", file=sys.stderr)
            continue
        found = True
        print(f"[{t:11}] {fm.get('name', path.stem):30} conf={fm.get('confidence', '?'):10} {fm.get('description', '')}")
    if not found:
        print("(no entries yet)")


def cmd_search(args):
    query = args.query.lower()
    hits = 0
    for t, path in iter_entries():
        try:
            fm, body = parse_frontmatter(path)
        except OSError as e:
            print(f"warning: skipping {path.relative_to(ROOT)}: {e}", file=sys.stderr)
            continue
        haystack = body.lower() + "\n" + "\n".join(str(v) for v in fm.values()).lower()
        if query in haystack:
            hits += 1
            print(f"[{t}] {fm.get('name', path.stem)} — {fm.get('description', '')}\n  {path.relative_to(ROOT)}")
    if not hits:
        print("(no matches)")


def cmd_show(args):
    for t, path in iter_entries():
        try:
            fm, _ = parse_frontmatter(path)
        except OSError as e:
            print(f"warning: skipping {path.relative_to(ROOT)}: {e}", file=sys.stderr)
            continue
        if fm.get("name") == args.name or path.stem == args.name:
            print(path.read_text(encoding="utf-8"))
            return
    print(f"no entry named '{args.name}'", file=sys.stderr)
    sys.exit(1)


def cmd_new(args):
    if args.type not in TYPES:
        print(f"type must be one of: {', '.join(TYPES)}", file=sys.stderr)
        sys.exit(1)
    if args.type == "prospective" and not args.due:
        print("--due is required for --type prospective", file=sys.stderr)
        sys.exit(1)
    if args.due:
        try:
            datetime.date.fromisoformat(args.due)
        except ValueError:
            print(f"--due is not a valid date: {args.due!r}", file=sys.stderr)
            sys.exit(1)
    slug = re.sub(r"[^a-z0-9]+", "-", args.name.lower()).strip("-")
    if not slug:
        print(f"name must contain at least one letter or digit: {args.name!r}", file=sys.stderr)
        sys.exit(1)
    folder = MEMORY / args.type
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{slug}.md"
    if dest.exists():
        print(f"entry already exists: {dest.relative_to(ROOT)}", file=sys.stderr)
        sys.exit(1)
    today = datetime.date.today().isoformat()
    try:
        text = TEMPLATE.read_text(encoding="utf-8")
    except OSError as e:
        print(f"error: could not read template {TEMPLATE}: {e}", file=sys.stderr)
        sys.exit(2)
    text = text.replace("REPLACE-ME-kebab-case-slug", slug)
    text = text.replace("type: semantic", f"type: {args.type}")
    text = text.replace("created: 1970-01-01", f"created: {today}")
    text = text.replace("last_verified: 1970-01-01", f"last_verified: {today}")
    if args.type == "prospective":
        text = text.replace("due: 1970-01-01", f"due: {args.due}")
    else:
        text = "".join(
            line for line in text.splitlines(keepends=True)
            if not line.startswith("due:")
        )
    dest.write_text(text, encoding="utf-8")
    print(f"created {dest.relative_to(ROOT)}")
    _append_log(args.type, slug, today)


def _append_log(entry_type, slug, today, action="created", detail=""):
    if not LOG_FILE.is_file():
        LOG_FILE.write_text(
            "# Ingest log\n\n"
            "Chronological record of entries added to and changed in the knowledge base.\n\n",
            encoding="utf-8",
        )
    suffix = f" — {detail}" if detail else ""
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"- {today} — {action} `{entry_type}/{slug}.md`{suffix}\n")


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
        rel = path.relative_to(ROOT)
        try:
            fm, _ = parse_frontmatter(path)
        except OSError as e:
            problems.append(f"{rel}: could not read file ({e})")
            continue
        name = fm.get("name", path.stem)

        if name in seen_names:
            problems.append(f"duplicate slug '{name}': {seen_names[name]} vs {rel}")
        else:
            seen_names[name] = rel

        confidence = fm.get("confidence")
        if confidence not in set(CONFIDENCE_LEVELS):
            problems.append(f"{rel}: missing/invalid confidence field")

        for field in required_fields:
            if not fm.get(field):
                problems.append(f"{rel}: missing required field '{field}' (see .kb/schema/entry.schema.json)")

        raw_name = fm.get("name")
        if raw_name and name_pattern and not re.match(name_pattern, raw_name):
            problems.append(f"{rel}: name '{raw_name}' does not match required pattern {name_pattern}")

        entry_type = fm.get("type")
        if entry_type and type_enum and entry_type not in type_enum:
            problems.append(f"{rel}: type '{entry_type}' is not one of {type_enum}")
        if entry_type and entry_type != t:
            problems.append(f"{rel}: type '{entry_type}' does not match its folder '{t}/'")

        if entry_type == "prospective":
            due = fm.get("due")
            if due:
                try:
                    due_date = datetime.date.fromisoformat(due)
                    if due_date < today:
                        warnings.append(f"{rel}: overdue, due {due} has passed")
                except ValueError:
                    problems.append(f"{rel}: due is not a valid date: {due!r}")

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

    # second pass for dangling links and inbound-link tracking, now that we know all names
    inbound = set()
    for t, path in iter_entries():
        rel = path.relative_to(ROOT)
        try:
            fm, _ = parse_frontmatter(path)
        except OSError:
            continue  # already reported in the first pass
        links = fm.get("links") or []
        if not isinstance(links, list):
            problems.append(f"{rel}: 'links' must be a list, got {links!r}")
            continue
        for link in links:
            if link not in seen_names:
                problems.append(f"{rel}: dangling link '{link}'")
            else:
                inbound.add(link)

    for name, rel in seen_names.items():
        if name not in inbound:
            warnings.append(f"{rel}: orphan entry, no other entry links to it")

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
    p_new.add_argument("--due", help="ISO date; required for --type prospective")
    p_new.set_defaults(func=cmd_new)

    p_lint = sub.add_parser("lint", help="schema, duplicate-slug, dangling-link, and staleness checks")
    p_lint.add_argument("--strict", action="store_true",
                         help="treat staleness/unverified-age warnings as fatal")
    p_lint.set_defaults(func=cmd_lint)

    p_triage = sub.add_parser("triage", help="queue of entries needing attention")
    p_triage.add_argument("--type", choices=TYPES, help="only this memory type")
    p_triage.add_argument("--reason", choices=sorted(TRIAGE_SEVERITY),
                          help="only entries flagged for this reason")
    p_triage.add_argument("--json", action="store_true", help="machine-readable output")
    p_triage.set_defaults(func=cmd_triage)

    p_verify = sub.add_parser("verify", help="stamp an entry as verified today")
    p_verify.add_argument("name")
    p_verify.add_argument("--confidence", choices=CONFIDENCE_LEVELS,
                          help="also set the confidence level")
    p_verify.set_defaults(func=cmd_verify)

    p_set = sub.add_parser("set", help="set a frontmatter field on an entry")
    p_set.add_argument("name")
    p_set.add_argument("field")
    p_set.add_argument("value")
    p_set.set_defaults(func=cmd_set)

    p_link = sub.add_parser("link", help="add or remove a link between entries")
    p_link.add_argument("name")
    p_link.add_argument("target")
    p_link.add_argument("--remove", action="store_true", help="remove the link instead")
    p_link.set_defaults(func=cmd_link)

    p_edit = sub.add_parser("edit", help="open an entry in $EDITOR")
    p_edit.add_argument("name")
    p_edit.add_argument("--editor", help="override $EDITOR")
    p_edit.set_defaults(func=cmd_edit)

    p_rm = sub.add_parser("rm", help="delete an entry")
    p_rm.add_argument("name")
    p_rm.add_argument("--force", action="store_true",
                      help="delete even if linked from elsewhere, stripping those links")
    p_rm.set_defaults(func=cmd_rm)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
