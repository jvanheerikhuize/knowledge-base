#!/usr/bin/env python3
"""Serve the knowledge base to any MCP client over stdio.

    python3 scripts/mcp_server.py [--read-only]

Speaks the Model Context Protocol so an agent can query this memory store as a
tool instead of shelling out to `kb.py` and parsing its printed output. Every
tool is a thin wrapper over the same functions the CLI and `serve.py` call, so
all three agree by construction.

Transport is stdio, framed as newline-delimited JSON-RPC: the spec requires
that nothing but MCP messages reach stdout, so this module logs to stderr and
never prints. That is also why the tools call kb.py's *library* functions
(`rank`, `context_pack`, `triage_report`) rather than its `cmd_*` handlers,
which print and sometimes call sys.exit.

Writes are proposals. `propose_update` and `capture` edit the working tree and
stop there — they never commit — so git stays the review gate and the durable
write path, exactly as `serve.py` settled it for the browser. Run with
`--read-only` to drop them entirely.

No third-party dependencies — stdlib only, same as the rest of the KB tooling.
"""
import argparse
import json
import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import kb  # noqa: E402

SERVER_NAME = "knowledge-base"
SERVER_VERSION = "1.0.0"

# Newest first. The client's requested version is echoed back when we know it;
# otherwise the spec says to answer with the latest we support and let the
# client decide whether to continue.
#
# 2026-07-28 is deliberately absent. It removes the initialize handshake in
# favour of per-request `_meta` and is a documented breaking change with no
# automatic compatibility, published the same day this server was written and
# still inside its SDK validation window. Nothing that would connect to this
# server speaks it yet. See ROADMAP.md Phase 2.
PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26"]
LATEST_PROTOCOL = PROTOCOL_VERSIONS[0]

INSTRUCTIONS = (
    "A file-based agent memory store, organised by memory type "
    "(semantic, episodic, procedural, prospective, retrieval, parametric, working).\n\n"
    "Start a task with `context` — it returns a budgeted, provenance-carrying brief "
    "of the most relevant entries, which is what this store exists to produce. "
    "Use `search` when you want ranked hits without the packaging, `get` to read one "
    "entry in full, and `triage`/`status` to see what needs attention.\n\n"
    "Every entry carries a confidence level and a `last_verified` date; trust them "
    "rather than assuming an entry is current. Writes via `propose_update` and "
    "`capture` are staged in the working tree for human review and are never "
    "committed. `capture` is how a new claim gets in: write the claim yourself, "
    "and it tells you which entry already holds it before anything is filed."
)

RESOURCE_PREFIX = "kb://entry/"
AGENT_URI = "kb://agent"

# JSON-RPC error codes. The last one is MCP's own.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
RESOURCE_NOT_FOUND = -32002


class ToolError(Exception):
    """A tool that failed for a reason the model should see and can act on.

    Reported inside the result with `isError`, not as a JSON-RPC error: protocol
    errors are for malformed requests, tool errors are feedback to the caller.
    """


class RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def log(message):
    """stderr is the only channel a stdio MCP server may talk on."""
    print(f"[{SERVER_NAME}] {message}", file=sys.stderr, flush=True)


# --- shared helpers ---------------------------------------------------------

def _all_entries():
    out = []
    for t, path in kb.iter_entries():
        try:
            fm, body = kb.parse_frontmatter(path)
        except OSError as e:
            log(f"skipping {path}: {e}")
            continue
        out.append((t, path, fm, body))
    return out


def _entry_name(path, fm):
    return fm.get("name", path.stem)


def _require_entry(name):
    hit = kb.resolve(name)
    if hit is None:
        raise ToolError(f"no entry named '{name}' — run the `search` tool to find the right one")
    return hit


def _strip_body(hits):
    return [{k: v for k, v in h.items() if k != "body"} for h in hits]


def _optional_type(args):
    t = args.get("type")
    if t is None:
        return None
    if t not in kb.TYPES:
        raise ToolError(f"type must be one of: {', '.join(kb.TYPES)}")
    return t


def _int(args, key, default):
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        try:
            value = int(value)
        except (TypeError, ValueError):
            raise ToolError(f"{key} must be an integer, got {args.get(key)!r}")
    return value


# --- tools ------------------------------------------------------------------

def tool_search(args):
    query = str(args.get("query") or "").strip()
    if not query:
        raise ToolError("query is required")
    limit = _int(args, "limit", 10)
    hits = kb.rank(query, types=[_optional_type(args)] if args.get("type") else None,
                   include_episodic=args.get("include_episodic", True),
                   include_archived=bool(args.get("include_archived", False)))
    hits = _strip_body(hits[:limit] if limit > 0 else hits)
    if not hits:
        return "(no matches)", {"query": query, "hits": []}
    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(f"{i:2}. {h['score']:6.2f}  [{h['type']}] {h['name']} — {h['description']}")
        lines.append(f"      {h['path']}  ·  confidence: {h['confidence'] or 'unknown'}"
                     f"  ·  last verified: {h['last_verified'] or 'never'}")
        if h["snippet"]:
            lines.append(f"      … {h['snippet']}")
    return "\n".join(lines), {"query": query, "hits": hits}


def tool_get(args):
    name = str(args.get("name") or "").strip()
    if not name:
        raise ToolError("name is required")
    entry_type, path, fm, body = _require_entry(name)
    return path.read_text(encoding="utf-8"), {
        "name": _entry_name(path, fm),
        "type": entry_type,
        "path": str(path.relative_to(kb.ROOT)),
        "frontmatter": fm,
        "body": body,
    }


def tool_history(args):
    """What one entry has said over time. Reads git; changes nothing."""
    name = str(args.get("name") or "").strip()
    if not name:
        raise ToolError("name is required")
    entry_type, path, fm, _ = _require_entry(name)
    entry_name = _entry_name(path, fm)
    revisions = kb.entry_history(path, limit=_int(args, "limit", 0))
    if revisions is None:
        raise ToolError(
            f"no history for '{entry_name}' — the knowledge base is not in a git "
            "repository, or git is unavailable")

    shallow = kb.history_is_shallow()
    payload = {
        "name": entry_name,
        "type": entry_type,
        "path": str(path.relative_to(kb.ROOT)),
        "shallow": shallow,
        "revisions": revisions,
    }
    if not revisions:
        return f"'{entry_name}' has never been committed — nothing to show yet", payload

    lines = [f"{entry_name} ({entry_type}) — {len(revisions)} revision(s), oldest first"]
    if shallow:
        lines.append("! shallow clone — this history is truncated")
    for revision in revisions:
        lines.append(f"  {revision['date']}  {revision['commit']}  "
                     f"{kb.HISTORY_CHANGES[revision['change']]:15} {revision['subject']}")
        if revision["change"] in ("created", "claim") and revision["claim"]:
            lines.append(f"      | {revision['claim']}")
    lines.append(f"\n{kb.HISTORY_CAVEAT}")
    return "\n".join(lines), payload


def tool_context(args):
    query = str(args.get("query") or "").strip()
    if not query:
        raise ToolError("query is required — describe the task you are about to work on")
    pack = kb.context_pack(
        query,
        budget=_int(args, "budget", kb.DEFAULT_CONTEXT_BUDGET),
        types=[_optional_type(args)] if args.get("type") else None,
        include_episodic=bool(args.get("include_episodic", False)),
        limit=_int(args, "limit", 0),
    )
    return pack["text"], {k: v for k, v in pack.items() if k != "text"}


def tool_triage(args):
    report = kb.triage_report()
    entry_type = _optional_type(args)
    if entry_type:
        report = [r for r in report if r["type"] == entry_type]
    reason = args.get("reason")
    if reason:
        report = [r for r in report if any(x["code"] == reason for x in r["reasons"])]
    if not report:
        # This is what an agent reads to decide the store is fine. It said
        # "nothing needs attention" while 78 pairs stood unjudged, because
        # `triage_report` reads one entry at a time and a pair is not an entry.
        load = kb.judgement_load()
        text = "triage clean — no entry needs attention"
        if load["owed"]:
            text += (f"\n{load['owed']} pair(s) await a ruling "
                     "(kb.py candidates / duplicate_candidates). A pair "
                     "nobody has judged is unexamined, not agreed.")
        return text, {"triage": [], "judgement_load": load}
    lines = []
    for r in report:
        lines.append(f"[{r['type']}] {r['name']} — {', '.join(x['code'] for x in r['reasons'])}")
        for x in r["reasons"]:
            lines.append(f"    - {x['code']}: {x['detail']}")
    lines.append(f"\n{len(report)} entr(ies) need attention")
    return "\n".join(lines), {"triage": report}


def tool_due(args):
    within = args.get("within")
    if within is not None:
        try:
            within = int(within)
            if within < 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ToolError(f"within must be a non-negative integer number of days, got {args.get('within')!r}")
    rows = kb.due_report(within_days=within)
    if not rows:
        scope = f" within {within}d" if within is not None else ""
        return f"nothing due{scope}", {"due": []}
    lines = []
    for r in rows:
        flag = "OVERDUE" if r["overdue"] else f"in {r['days']}d"
        lines.append(f"[{flag}] {r['due']}  {r['name']} — {r['description']}")
    lines.append(f"\n{len(rows)} entr(ies) due")
    return "\n".join(lines), {"due": rows}


def tool_status(args):
    report = kb.status_report()
    entry_type = _optional_type(args)
    if entry_type:
        report = [r for r in report if r["type"] == entry_type]
    wanted = args.get("status")
    if wanted:
        if wanted not in kb.STATUS_ORDER:
            raise ToolError(f"status must be one of: {', '.join(kb.STATUS_ORDER)}")
        report = [r for r in report if r["status"] == wanted]
    if not report:
        return "no entries match", {"entries": [], "counts": {}}
    counts = {}
    lines = []
    for r in report:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        age = f"{r['age_days']}d ago" if r["age_days"] is not None else "never verified"
        lines.append(f"[{r['label']}] {r['name']} ({r['type']}) — {age}; → {r['action']}")
    summary = "  ".join(f"{kb.STATUS_BY_KEY[k]['label'].lower()}: {counts[k]}"
                        for k in kb.STATUS_ORDER if counts.get(k))
    lines.append(f"\n{len(report)} entries — {summary}")
    return "\n".join(lines), {"entries": report, "counts": counts}


def tool_dupes(args):
    threshold = args.get("threshold", kb.DUPES_THRESHOLD)
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        raise ToolError(f"threshold must be a number, got {args.get('threshold')!r}")
    pairs, skipped = kb.dupe_pairs(threshold=threshold)
    limit = (
        "This finds text recorded twice, not the same claim written twice — "
        "a paraphrase of an existing entry measured below thirteen pairs of "
        "merely-related entries on this store. A clean result does not mean "
        "there are no duplicates."
    )
    if not pairs:
        text = f"no near-duplicate pairs above {threshold}\n\n{limit}"
    else:
        lines = []
        for p in pairs:
            flag = " (already linked)" if p["linked"] else ""
            lines.append(f"{max(p['jaccard'], p['containment']):.2f}  "
                         f"{p['a']} <-> {p['b']}{flag}")
            lines.append(f"      jaccard {p['jaccard']}  containment {p['containment']}")
        lines.append(f"\n{len(pairs)} pair(s) above {threshold}. Read both, merge by "
                     f"hand, then archive the loser.\n\n{limit}")
        text = "\n".join(lines)
    return text, {"threshold": threshold, "pairs": pairs, "too_short": skipped}


def tool_candidates(args):
    """The recall half: hand back a short list of pairs, and decline to rule."""
    neighbours = args.get("neighbours", kb.NEIGHBOURS)
    try:
        neighbours = int(neighbours)
    except (TypeError, ValueError):
        raise ToolError(f"neighbours must be an integer, got {args.get('neighbours')!r}")
    if neighbours < 1:
        raise ToolError("neighbours must be at least 1")
    include_judged = bool(args.get("include_judged"))
    pairs, skipped = kb.candidate_pairs(neighbours=neighbours,
                                        include_judged=include_judged)
    caveat = (
        "These are candidates, not duplicates — roughly one pair in three to "
        "eight is a real restatement, and no score here tells you which. Read "
        "both entries in full (kb://entry/<name> or the `get` tool) and record "
        "the call with `judge`. Answer BOTH questions: how much the two "
        "overlap (`verdict`), and whether they disagree (`agreement`). A pair "
        "left unanswered on the second stays in this queue — no score finds "
        "contradictions, so an agent reading the pair is the only detector "
        "there is."
    )
    if not pairs:
        text = f"no unjudged candidate pairs at {neighbours} neighbour(s) per entry"
    else:
        lines = []
        for p in pairs:
            tags = []
            if p["linked"]:
                tags.append("already linked")
            if p["verdict"]:
                tags.append(f"judged {p['verdict']} {p['judged']}"
                            + (" — TEXT CHANGED SINCE" if p["verdict_stale"] else ""))
            if p["agreement"] == "contradict":
                tags.append("CONTRADICTION standing — reconcile them")
            elif p["verdict"] and not p["agreement"] and not p["verdict_stale"]:
                tags.append("never checked for contradiction")
            suffix = f"  ({'; '.join(tags)})" if tags else ""
            lines.append(f"{p['similarity']:.2f}  {p['a']} <-> {p['b']}{suffix}")
            lines.append(f"      a: {p['a_description']}")
            lines.append(f"      b: {p['b_description']}")
        lines.append(f"\n{len(pairs)} pair(s) to judge.\n\n{caveat}")
        text = "\n".join(lines)
    return text, {"neighbours": neighbours, "pairs": pairs, "too_short": skipped}


def tool_consolidate(args):
    """What the standing verdicts still owe. Proposals only — it writes nothing."""
    margin = args.get("margin", kb.RESTATEMENT_MARGIN)
    try:
        margin = float(margin)
    except (TypeError, ValueError):
        raise ToolError(f"margin must be a number, got {args.get('margin')!r}")
    if margin < 1:
        raise ToolError("margin must be at least 1")
    report = kb.consolidation_report(
        margin=margin, include_dismissed=bool(args.get("include_dismissed")))
    merges, edges = report["merges"], report["missing_edges"]
    restated = report["restatements"]

    lines = [f"MERGE — pairs standing at 'duplicate' ({len(merges)})"]
    for p in merges:
        lines.append(f"  {p['a']} <-> {p['b']}   (judged {p['judged']})"
                     + (f"  note: {p['note']}" if p["note"] else ""))
    lines.append(f"\nLINK — judged 'overlap', no edge between them ({len(edges)})")
    for p in edges:
        lines.append(f"  {p['a']} <-> {p['b']}   (judged {p['judged']})"
                     + (f"  note: {p['note']}" if p["note"] else ""))
    lines.append(f"\nRESTATED — passages that read as another entry's ({len(restated)})")
    for p in restated:
        # Only the informative half of `linked` is shown; see cmd_consolidate.
        tags = [] if p["linked"] else ["no edge between them"]
        if p["mentions_target"]:
            tags.append("passage already cites it")
        if p["verdict"]:
            tags.append(f"judged {p['verdict']}")
        if p["dismissed"]:
            tags.append(f"dismissed {p['dismissed']}")
        suffix = f"  ({'; '.join(tags)})" if tags else ""
        lines.append(f"  [{p['id']}] {p['host']} -> {p['target']}{suffix}")
        lines.append(f"      | {p['passage'][:200]}")
    if report["dismissed_restatements"] and not args.get("include_dismissed"):
        lines.append(f"\n  {report['dismissed_restatements']} passage(s) read "
                     "and dismissed earlier are hidden. Editing one puts it "
                     "back; pass include_dismissed to see them.")
    lines.append(
        "\nProposals, not decisions. Each one is a judgement you make by "
        "reading the entries: a missing link is an edge somebody decided was "
        "not worth drawing, and most restated passages are an entry "
        "legitimately discussing its neighbour. Apply the ones that are real "
        "with `propose_update` (link) or by rewriting the passage; record the "
        "rest with `dismiss` so the next reader is not handed them again."
    )
    return "\n".join(lines), report


def tool_judge(args):
    """Stage a verdict about one pair. Like every write here, it does not commit."""
    verdict = str(args.get("verdict") or "").strip()
    if verdict not in kb.VERDICTS:
        raise ToolError(f"verdict must be one of: {', '.join(kb.VERDICTS)}")
    agreement = str(args.get("agreement") or "").strip() or None
    if agreement and agreement not in kb.AGREEMENTS:
        raise ToolError(f"agreement must be one of: {', '.join(kb.AGREEMENTS)}")
    a_name = str(args.get("a") or "").strip()
    b_name = str(args.get("b") or "").strip()
    if not a_name or not b_name:
        raise ToolError("both a and b are required")
    _, a_path, a_fm, a_body = _require_entry(a_name)
    _, b_path, b_fm, b_body = _require_entry(b_name)
    a_resolved = _entry_name(a_path, a_fm)
    b_resolved = _entry_name(b_path, b_fm)
    if a_resolved == b_resolved:
        raise ToolError("an entry cannot duplicate itself")
    kb.record_verdict(a_resolved, a_fm, a_body, b_resolved, b_fm, b_body,
                      verdict, args.get("note"), agreement)
    if agreement == "contradict":
        follow_up = ("both entries are now `contradicted` in triage and status. "
                     "Reconcile them — correct the wrong one, or narrow both "
                     "until they can both be true — then re-judge with "
                     "agreement=agree")
    else:
        follow_up = {
            "duplicate": "merge the two by hand and archive the loser — this pair "
                         "stays in the candidate queue until you do",
            "overlap": "related, but both earn their place; link them if they are "
                       "not linked already",
            "distinct": "this pair leaves the queue unless either entry's text changes",
        }[verdict]
        if not agreement:
            follow_up += ("; and you have only half-judged it — no `agreement` "
                          "means nobody has asked whether the two disagree, so "
                          "the pair stays in the queue")
    agreed = f" ({agreement})" if agreement else ""
    text = (f"recorded (staged, not committed): {a_resolved} <-> {b_resolved} "
            f"= {verdict}{agreed}\nnext: {follow_up}")
    return text, {"a": a_resolved, "b": b_resolved, "verdict": verdict,
                  "agreement": agreement,
                  "file": str(kb.VERDICTS_FILE.relative_to(kb.ROOT)),
                  "committed": False}


def tool_dismiss(args):
    """Stage a ruling that a restated passage belongs where it is.

    Resolved against the live queue, like the CLI: an id that matches nothing
    is a passage edited since it was listed, and a ruling filed against text
    nobody read is worse than no ruling.
    """
    ids = args.get("ids")
    if isinstance(ids, str):
        ids = [ids]
    ids = [str(i).strip() for i in (ids or []) if str(i).strip()]
    if not ids:
        raise ToolError("ids is required — one or more proposal ids from "
                        "`consolidate`")
    proposals = {p["id"]: p for p in kb.restatements()}
    unknown = [i for i in ids if i not in proposals]
    if unknown:
        raise ToolError(
            f"no live proposal with id: {', '.join(unknown)}. Run "
            "`consolidate` for current ids — a passage edited since it was "
            "listed gets a new one")
    note = str(args.get("note") or "").strip()
    for i in ids:
        p = proposals[i]
        kb.record_dismissal(p["host"], p["target"], p["passage"], note)
    done = "\n".join(f"  [{i}] {proposals[i]['host']} -> "
                     f"{proposals[i]['target']}" for i in ids)
    text = (f"dismissed (staged, not committed):\n{done}\n"
            "These stay out of `consolidate` until their text changes.")
    if not note:
        text += ("\nNo note recorded: nothing now says why the passage belongs "
                 "where it is, only that somebody wanted the queue shorter.")
    return text, {"ids": ids,
                  "file": str(kb.PASSAGES_FILE.relative_to(kb.ROOT)),
                  "committed": False}


def tool_propose_update(args):
    """Stage an edit in the working tree. Never commits — that is the point."""
    name = str(args.get("name") or "").strip()
    if not name:
        raise ToolError("name is required")
    entry_type, path, fm, _ = _require_entry(name)
    resolved = _entry_name(path, fm)
    changes = {}

    if "description" in args:
        desc = str(args["description"]).strip()
        if not desc:
            raise ToolError("description cannot be empty")
        changes["description"] = desc

    if "confidence" in args:
        conf = str(args["confidence"]).strip()
        if conf not in kb.CONFIDENCE_LEVELS:
            raise ToolError(f"confidence must be one of: {', '.join(kb.CONFIDENCE_LEVELS)}")
        changes["confidence"] = conf

    if "links" in args:
        links = args["links"]
        if not isinstance(links, list):
            raise ToolError("links must be a list of entry names")
        links = [str(x).strip() for x in links if str(x).strip()]
        known = {_entry_name(p, f) for _, p, f, _ in _all_entries()}
        for target in links:
            if target == resolved:
                raise ToolError("an entry cannot link to itself")
            if target not in known:
                raise ToolError(f"no entry named '{target}' — refusing to create a dangling link")
        changes["links"] = links

    verify_note = args.get("verify_note")
    if verify_note is not None and not args.get("verify"):
        raise ToolError("verify_note only means something with verify: true")
    if args.get("verify"):
        changes["last_verified"] = date.today().isoformat()

    if "archive" in args:
        if args["archive"]:
            if kb.is_archived(fm):
                raise ToolError(f"'{resolved}' is already archived (since {fm['archived']})")
            changes["archived"] = date.today().isoformat()
        else:
            if not kb.is_archived(fm):
                raise ToolError(f"'{resolved}' is not archived")
            changes["archived"] = None

    body = args.get("body")
    if body is not None and not str(body).strip():
        raise ToolError("body cannot be emptied — omit it to leave the body alone")

    if not changes and body is None:
        raise ToolError("nothing to change — pass description, confidence, links, body, or verify")

    if changes:
        kb.write_frontmatter(path, changes)
    if body is not None:
        kb.write_body(path, str(body))

    changed = sorted(set(changes) | ({"body"} if body is not None else set()))
    kb._append_log(entry_type, path.stem, date.today().isoformat(), "updated",
                   ", ".join(changed))
    if args.get("verify"):
        # Logged separately from the 'updated' record so `kb.py log --action
        # verified` shows every re-verification, whichever surface made it —
        # the CLI's and this one's trails are otherwise not comparable.
        kb._append_log(entry_type, path.stem, date.today().isoformat(), "verified",
                       kb.verify_detail(changes.get("confidence")
                                        or fm.get("confidence", "?"), verify_note))
    rel = str(path.relative_to(kb.ROOT))
    log(f"staged {', '.join(changed)} on {rel}")
    text = (
        f"Staged {', '.join(changed)} on {rel}.\n\n"
        "The change is in the working tree and has NOT been committed. Review it with\n"
        f"    git diff -- {rel}\n"
        "and commit it yourself if it is right."
    )
    return text, {"name": resolved, "path": rel, "changed": changed,
                  "committed": False, "review": f"git diff -- {rel}"}


def tool_capture(args):
    """Check a claim against the store, then file it — staged, never committed.

    Same three modes as `kb.py capture`: report the nearest entries and stop
    (the default), append the passage to an entry you decide it belongs in, or
    write it as a new `unverified` entry with the top neighbour prefilled as
    its one link.
    """
    passage = str(args.get("passage") or "").strip()
    if not passage:
        raise ToolError("passage is required — capture files a claim you have written")

    neighbours = kb.nearest_entries(passage)
    lines = [f"  {n['score']:6.1f}  {n['name']}"
             + (f"  <- {n['ratio']}x the runner-up" if n["decisive"] else "")
             for n in neighbours]
    nearest = ("Nearest entries:\n" + "\n".join(lines)) if lines else \
        "Nothing in the store reads like this passage."

    extend = str(args.get("extend") or "").strip()
    name = str(args.get("name") or "").strip()
    entry_type = str(args.get("type") or "").strip()

    if extend and (name or entry_type):
        raise ToolError("pass either extend, or type+name — not both")

    if extend:
        target_type, path, fm, body = _require_entry(extend)
        kb.write_body(path, f"{body.rstrip()}\n\n{passage}")
        kb._append_log(target_type, path.stem, date.today().isoformat(),
                       "extended", "captured passage appended")
        rel = str(path.relative_to(kb.ROOT))
        log(f"appended a captured passage to {rel}")
        return (
            f"Appended the passage to {rel}.\n\n"
            "Staged in the working tree, NOT committed. Appending is not "
            f"verification — re-read the entry, then review with\n    git diff -- {rel}"
        ), {"extended": _entry_name(path, fm), "path": rel, "committed": False}

    if not (name and entry_type):
        return (
            f"{nearest}\n\n"
            "Nothing written. Read the top entry before you file this: if the "
            "passage restates it, call capture again with `extend` set to that "
            "entry; if it is genuinely new, call capture again with `type` and "
            "`name`."
        ), {"neighbours": neighbours, "written": False}

    top = neighbours[0]["name"] if neighbours else None
    try:
        dest = kb.scaffold_entry(
            entry_type, name, due=args.get("due"),
            description=str(args.get("description") or "").strip()
            or kb._first_sentence(passage),
            body=passage, links=[top] if top else [],
            source=str(args.get("source") or "").strip() or "captured passage",
        )
    except kb.EntryError as e:
        raise ToolError(str(e)) from None
    rel = str(dest.relative_to(kb.ROOT))
    log(f"staged new entry {rel}")
    return (
        f"{nearest}\n\nWrote {rel} with confidence `unverified`"
        + (f", linked to {top}" if top else "")
        + ".\n\nStaged in the working tree and NOT committed. Read it back, set "
        "confidence honestly, add whichever of the entries above belong in "
        f"`links`, then review with\n    git diff -- {rel}"
    ), {"name": dest.stem, "path": rel, "links": [top] if top else [],
        "neighbours": neighbours, "committed": False}


READ_TOOLS = [
    {
        "name": "context",
        "title": "Context pack for a task",
        "description": (
            "The one call to make at the start of a task. Returns a budgeted, "
            "paste-ready brief of the most relevant memory entries, each with its "
            "confidence, last-verified date, and source file. Episodic logs are "
            "excluded by default because they describe one past run."
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "the task you are about to work on"},
                "budget": {"type": "integer",
                           "description": f"approximate token budget (default {kb.DEFAULT_CONTEXT_BUDGET})"},
                "limit": {"type": "integer",
                          "description": "cap on entries considered (0 for no cap)"},
                "type": {"type": "string", "enum": kb.TYPES,
                         "description": "restrict to one memory type"},
                "include_episodic": {"type": "boolean",
                                     "description": "include episodic logs (default false)"},
            },
            "required": ["query"],
        },
        "handler": tool_context,
    },
    {
        "name": "search",
        "title": "Ranked search",
        "description": (
            "BM25 search across the whole store, best first. Ranking is type-aware: "
            "a term in an entry's name counts for more than one in the body, "
            "procedures and facts outrank scratch files, recency applies to episodic "
            "entries only, and confidence nudges near-ties."
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "what to look for"},
                "limit": {"type": "integer", "description": "hits to return (0 for all; default 10)"},
                "type": {"type": "string", "enum": kb.TYPES,
                         "description": "restrict to one memory type"},
                "include_episodic": {"type": "boolean",
                                     "description": "include episodic logs (default true)"},
                "include_archived": {"type": "boolean",
                                     "description": "include entries retired from retrieval (default false)"},
            },
            "required": ["query"],
        },
        "handler": tool_search,
    },
    {
        "name": "get",
        "title": "Read one entry",
        "description": "Return one entry in full — raw markdown plus parsed frontmatter.",
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "entry name or filename stem"}},
            "required": ["name"],
        },
        "handler": tool_get,
    },
    {
        "name": "triage",
        "title": "What needs attention",
        "description": (
            "The queue of entries that are wrong or ageing — overdue reminders, stale "
            "facts, unverified claims, broken dates, orphans — worst first."
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": kb.TYPES},
                "reason": {"type": "string", "enum": sorted(kb.TRIAGE_SEVERITY),
                           "description": "only entries flagged for this reason"},
            },
        },
        "handler": tool_triage,
    },
    {
        "name": "due",
        "title": "What's coming due",
        "description": (
            "Prospective entries whose `due:` date has arrived or is approaching, "
            "soonest first. Unlike `triage`, this surfaces a due date before it "
            "lapses, not just after."
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "within": {"type": "integer", "minimum": 0,
                           "description": "only entries due within this many days "
                                          "(overdue entries always show)"},
            },
        },
        "handler": tool_due,
    },
    {
        "name": "status",
        "title": "Where every entry stands",
        "description": (
            "Every entry with the one status that describes it and the single command "
            "that moves it on. Triage lists what is already wrong; status accounts for "
            "everything, so 'clean' cannot quietly mean 'unexamined'."
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": kb.TYPES},
                "status": {"type": "string", "enum": kb.STATUS_ORDER},
            },
        },
        "handler": tool_status,
    },
    {
        "name": "dupes",
        "title": "Near-verbatim duplicate pairs",
        "description": (
            "Entry pairs whose text overlaps near-verbatim — the same text "
            "recorded twice. It does NOT find two entries making the same claim "
            "in different words: that was measured and lexical similarity ranks "
            "topical neighbours above real restatements. Treat a clean result as "
            "'no copies found', never as 'no duplicates'."
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "threshold": {"type": "number",
                              "description": f"minimum jaccard or containment "
                                             f"(default {kb.DUPES_THRESHOLD}); lowering it "
                                             f"yields false positives before it yields "
                                             f"paraphrases"},
            },
        },
        "handler": tool_dupes,
    },
    {
        "name": "duplicate_candidates",
        "title": "Pairs that may say the same thing in different words",
        "description": (
            "The half `dupes` cannot do. Returns each entry's nearest neighbours "
            "as a short list of pairs for YOU to judge by reading them — no score "
            "here decides anything, and most pairs will be merely related. "
            "Pairs already judged drop out; a pair judged `duplicate` stays until "
            "it is merged, a pair judged to contradict stays until it is "
            "reconciled, and any pair whose entries have been rewritten since "
            "comes back. This is also the store's only contradiction check — "
            "measured, no cheap signal separates 'these two disagree' from "
            "'these two are about the same thing', so reading the pair is the "
            "detector. Record every call with `judge` so the next agent does "
            "not repeat the reading."
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "neighbours": {"type": "integer",
                               "description": f"nearest neighbours per entry "
                                              f"(default {kb.NEIGHBOURS}); higher trades "
                                              f"more pairs to read for more recall"},
                "include_judged": {"type": "boolean",
                                   "description": "also return pairs already settled "
                                                  "on both axes"},
            },
        },
        "handler": tool_candidates,
    },
    {
        "name": "consolidate",
        "title": "What the standing verdicts still owe",
        "description": (
            "`judge` records what two entries are to each other; this reports "
            "what nobody has done about it. Three queues: pairs judged "
            "`duplicate` that were never merged; pairs judged `overlap` with "
            "no link between them — a defect `lint` cannot see, because a "
            "missing edge is a property of a pair and lint only checks single "
            "entries; and passages that score higher against a different entry "
            "than against their own, which is how a paragraph restating "
            "another entry is found (shingle overlap does not find it — "
            "measured, 1 of 7 against 7 of 7). Proposals only, it changes "
            "nothing. Most restated passages are an entry legitimately "
            "discussing its neighbour, so read before acting — and record the "
            "ones you leave with `dismiss`, or the next reader gets them all "
            "again."
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "margin": {"type": "number",
                           "description": f"how far a passage's best entry must "
                                          f"beat the runner-up (default "
                                          f"{kb.RESTATEMENT_MARGIN}); lower trades "
                                          f"more passages to read for more recall"},
                "include_dismissed": {
                    "type": "boolean",
                    "description": "also return passages already read and "
                                   "dismissed"},
            },
        },
        "handler": tool_consolidate,
    },
    {
        "name": "history",
        "title": "What one entry has said over time",
        "description": (
            "The revisions of one entry, oldest first, each labelled with what "
            "it changed: the claim itself, the body, or only bookkeeping "
            "(`verify` and `link` touch an entry far more often than an author "
            "does, and an unlabelled log buries the rewrites under them). "
            "Where the one-line claim changed, the superseded wording is "
            "quoted. Entries here are corrected in place rather than retired "
            "on a date, so this is the only record of what the current claim "
            "replaced — read it before trusting an entry you are about to "
            "contradict."
        ),
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "entry name or filename stem"},
                "limit": {"type": "integer",
                          "description": "show only the most recent N revisions "
                                         "(0 or omitted for all)"},
            },
            "required": ["name"],
        },
        "handler": tool_history,
    },
]

WRITE_TOOLS = [
    {
        "name": "judge",
        "title": "Record a verdict on one candidate pair (staged, not committed)",
        "description": (
            "Write down what you concluded about a pair, so the judgement "
            "outlives your context and nobody re-reads the pair. TWO answers, "
            "not one. `verdict` is how much they overlap: `duplicate` = the "
            "same claim twice, merge them; `overlap` = related, both earn their "
            "place; `distinct` = different claims that happen to share vocabulary. "
            "`agreement` is the independent question of whether they DISAGREE: "
            "`agree` = both can be true, `contradict` = they cannot, so one of "
            "them is wrong and both entries go to `contradicted` in triage. "
            "Omitting `agreement` records the pair as unexamined on that axis "
            "and leaves it in the queue — it is not a way to say 'fine'. "
            "Both answers are bound to the text you judged: rewrite either entry "
            "and the pair returns for a fresh look."
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "a": {"type": "string", "description": "one entry of the pair"},
                "b": {"type": "string", "description": "the other entry"},
                "verdict": {"type": "string", "enum": list(kb.VERDICTS),
                            "description": "how much the two overlap"},
                "agreement": {"type": "string", "enum": list(kb.AGREEMENTS),
                              "description": "whether they can both be true; "
                                             "omit only if you did not look"},
                "note": {"type": "string",
                         "description": "one line on why, kept with the verdict"},
            },
            "required": ["a", "b", "verdict"],
        },
        "handler": tool_judge,
    },
    {
        "name": "dismiss",
        "title": "Record that a restated passage belongs where it is (staged)",
        "description": (
            "The other half of `consolidate`: say that you read a proposed "
            "passage and it stays put. Without it the queue has no memory — "
            "measured over this store's history, 90% of what it puts up is a "
            "passage it had already put up before, some unchanged since the "
            "store held ten entries — so every reader pays for every earlier "
            "reader's work. Pass the id(s) `consolidate` printed. The ruling "
            "is bound to the passage text: edit the passage and it returns, "
            "which is why acting on a proposal needs no separate verdict."
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "string"},
                        "description": "proposal id(s) from `consolidate`"},
                "note": {"type": "string",
                         "description": "one line on why it belongs where it "
                                        "is, kept with the ruling"},
            },
            "required": ["ids"],
        },
        "handler": tool_dismiss,
    },
    {
        "name": "propose_update",
        "title": "Propose an edit (staged, not committed)",
        "description": (
            "Stage an edit to an existing entry in the working tree for human review. "
            "This never commits: git remains the durable write path and the review "
            "gate. Links are checked so a proposal cannot dangle."
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": True, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "entry to edit"},
                "description": {"type": "string", "description": "new one-line description"},
                "confidence": {"type": "string", "enum": kb.CONFIDENCE_LEVELS},
                "links": {"type": "array", "items": {"type": "string"},
                          "description": "replacement link list; every target must exist"},
                "body": {"type": "string", "description": "replacement body markdown"},
                "verify": {"type": "boolean",
                           "description": "stamp last_verified as today"},
                "verify_note": {"type": "string",
                                "description": "with verify: what you actually checked, "
                                               "and against what — the date records the "
                                               "schedule, this records the evidence"},
                "archive": {"type": "boolean",
                            "description": "true retires the entry from retrieval (it stays "
                                           "readable and linked); false puts it back"},
            },
            "required": ["name"],
        },
        "handler": tool_propose_update,
    },
    {
        "name": "capture",
        "title": "File a claim you have written (staged, not committed)",
        "description": (
            "Put a claim you have already written into the store, with the "
            "check this store asks an author to do by hand run first: which "
            "existing entries does this passage read like? Call it with only "
            "`passage` to see that answer and write nothing. Then call it "
            "again — with `extend` if the passage restates an entry the store "
            "already holds (better a fuller entry than a near-twin), or with "
            "`type` and `name` to file it as a new `unverified` entry. This "
            "does NOT extract facts from a transcript for you: the claim has "
            "to be one you can state, because the deciding is the work."
        ),
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": False},
        "inputSchema": {
            "type": "object",
            "properties": {
                "passage": {"type": "string",
                            "description": "the claim, in your words"},
                "type": {"type": "string", "enum": list(kb.TYPES),
                         "description": "memory type; with `name`, files a new entry"},
                "name": {"type": "string", "description": "slug for the new entry"},
                "description": {"type": "string",
                                "description": "one-line summary; defaults to the "
                                               "passage's first sentence"},
                "due": {"type": "string",
                        "description": "ISO date; required for type `prospective`"},
                "source": {"type": "string",
                           "description": "where the claim came from"},
                "extend": {"type": "string",
                           "description": "append the passage to this existing entry "
                                          "instead of writing a new one"},
            },
            "required": ["passage"],
        },
        "handler": tool_capture,
    },
]


def tool_table(read_only):
    tools = READ_TOOLS if read_only else READ_TOOLS + WRITE_TOOLS
    return {t["name"]: t for t in tools}


# --- resources --------------------------------------------------------------

def list_resources():
    resources = []
    agent_md = kb.MEMORY / "AGENT.md"
    if agent_md.is_file():
        resources.append({
            "uri": AGENT_URI,
            "name": "AGENT.md",
            "title": "Agent entry point",
            "description": "How this memory store is organised and how to write to it.",
            "mimeType": "text/markdown",
        })
    for t, path, fm, _ in _all_entries():
        name = _entry_name(path, fm)
        # An archived entry stays listed — it is still readable, and dropping
        # it would leave a client no way to find the entry it wants to
        # un-archive. But a resource listing is a discovery surface an agent
        # picks from, and every *other* surface on this server (`search`,
        # `context`, `triage`) already keeps retired claims out of the choices.
        # Listed and unlabelled is the one combination that misleads, so the
        # label travels with it, in both fields a client is likely to show.
        archived = kb.is_archived(fm)
        title = f"{name} ({t}, archived)" if archived else f"{name} ({t})"
        description = fm.get("description", "")
        if archived:
            description = f"[archived] {description}"
        resources.append({
            "uri": RESOURCE_PREFIX + name,
            "name": name,
            "title": title,
            "description": description,
            "mimeType": "text/markdown",
        })
    return resources


def read_resource(uri):
    if uri == AGENT_URI:
        path = kb.MEMORY / "AGENT.md"
        if not path.is_file():
            raise RpcError(RESOURCE_NOT_FOUND, f"resource not found: {uri}")
        return {"uri": uri, "mimeType": "text/markdown",
                "text": path.read_text(encoding="utf-8")}
    if not uri.startswith(RESOURCE_PREFIX):
        raise RpcError(RESOURCE_NOT_FOUND, f"resource not found: {uri}")
    name = uri[len(RESOURCE_PREFIX):]
    hit = kb.resolve(name)
    if hit is None:
        raise RpcError(RESOURCE_NOT_FOUND, f"resource not found: {uri}")
    _, path, _, _ = hit
    return {"uri": uri, "mimeType": "text/markdown",
            "text": path.read_text(encoding="utf-8")}


RESOURCE_TEMPLATES = [
    {
        "uriTemplate": RESOURCE_PREFIX + "{name}",
        "name": "Memory entry",
        "title": "Memory entry by name",
        "description": "One entry of the knowledge base, addressed by its name.",
        "mimeType": "text/markdown",
    },
]


# --- JSON-RPC ---------------------------------------------------------------

class Server:
    def __init__(self, read_only=False):
        self.read_only = read_only
        self.tools = tool_table(read_only)

    def initialize(self, params):
        requested = params.get("protocolVersion")
        version = requested if requested in PROTOCOL_VERSIONS else LATEST_PROTOCOL
        client = (params.get("clientInfo") or {}).get("name", "unknown client")
        log(f"{client} connected, protocol {version}"
            f"{' (read-only)' if self.read_only else ''}")
        return {
            "protocolVersion": version,
            "capabilities": {
                "tools": {},
                "resources": {},
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "title": "Agent memory knowledge base",
                "version": SERVER_VERSION,
            },
            "instructions": INSTRUCTIONS,
        }

    def call_tool(self, params):
        name = params.get("name")
        tool = self.tools.get(name)
        if tool is None:
            if name in {t["name"] for t in WRITE_TOOLS}:
                raise RpcError(INVALID_PARAMS,
                               f"tool '{name}' is disabled: this server is running --read-only")
            raise RpcError(INVALID_PARAMS, f"unknown tool: {name!r}")
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise RpcError(INVALID_PARAMS, "arguments must be an object")
        try:
            text, structured = tool["handler"](arguments)
        except ToolError as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except (OSError, ValueError) as e:
            log(f"{name} failed: {type(e).__name__}: {e}")
            return {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                    "isError": True}
        return {
            "content": [{"type": "text", "text": text}],
            "structuredContent": structured,
            "isError": False,
        }

    def handle(self, method, params):
        if method == "initialize":
            return self.initialize(params)
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [{k: v for k, v in t.items() if k != "handler"}
                              for t in self.tools.values()]}
        if method == "tools/call":
            return self.call_tool(params)
        if method == "resources/list":
            return {"resources": list_resources()}
        if method == "resources/templates/list":
            return {"resourceTemplates": RESOURCE_TEMPLATES}
        if method == "resources/read":
            uri = params.get("uri")
            if not uri:
                raise RpcError(INVALID_PARAMS, "uri is required")
            return {"contents": [read_resource(uri)]}
        raise RpcError(METHOD_NOT_FOUND, f"method not found: {method}")


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def dispatch(server, message):
    """One request in, one response out — or None for a notification."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "expected a JSON-RPC 2.0 object")
    method = message.get("method")
    if not isinstance(method, str):
        return _error(message.get("id"), INVALID_REQUEST, "missing method")
    params = message.get("params") or {}
    if not isinstance(params, dict):
        return _error(message.get("id"), INVALID_PARAMS, "params must be an object")

    is_notification = "id" not in message
    try:
        result = server.handle(method, params)
    except RpcError as e:
        if is_notification:
            return None
        return _error(message["id"], e.code, str(e))
    except Exception as e:  # never let one bad request kill the connection
        log(f"{method} raised {type(e).__name__}: {e}")
        if is_notification:
            return None
        return _error(message["id"], INTERNAL_ERROR, f"{type(e).__name__}: {e}")

    if is_notification:
        return None
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}


def serve(stdin=None, stdout=None, read_only=False):
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    server = Server(read_only=read_only)
    log(f"serving {kb.MEMORY} over stdio "
        f"({len(server.tools)} tools, protocol {LATEST_PROTOCOL})")
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as e:
            response = _error(None, PARSE_ERROR, f"invalid JSON: {e}")
        else:
            if isinstance(message, list):
                # Batching was removed from the protocol in 2025-06-18.
                response = _error(None, INVALID_REQUEST, "batch requests are not supported")
            else:
                response = dispatch(server, message)
        if response is None:
            continue
        # json.dumps escapes newlines inside strings, so a message is always
        # exactly one line — which the stdio transport requires.
        stdout.write(json.dumps(response) + "\n")
        stdout.flush()
    log("stdin closed, exiting")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Serve the knowledge base over MCP (stdio).")
    ap.add_argument("--read-only", action="store_true",
                    help="expose only the read tools; drop propose_update entirely")
    args = ap.parse_args(argv)
    try:
        return serve(read_only=args.read_only)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
