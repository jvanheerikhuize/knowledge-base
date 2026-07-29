#!/usr/bin/env python3
"""Interface layer for the file-based agent memory knowledge base.

No third-party dependencies — stdlib only, so the KB stays infra-free.
Run `kb.py --help` for usage.
"""
import argparse
import collections
import datetime
import hashlib
import json
import math
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
# How close to STALE_DAYS an entry gets before it is called out as ageing.
AGEING_RATIO = 2 / 3

# Every entry sits in exactly one of these states. Ordered worst first: an
# entry that qualifies for several takes the earliest one, so the status
# answers "what is the single next thing to do about this entry".
# `action` is the literal command that moves it out of the state.
STATUS_MODEL = [
    {
        "key": "broken",
        "label": "Broken metadata",
        "meaning": "A date in the frontmatter cannot be parsed, so this entry "
                   "escapes every freshness check.",
        "action": "kb.py set <name> last_verified YYYY-MM-DD",
    },
    {
        "key": "overdue",
        "label": "Overdue",
        "meaning": "A prospective entry whose due date has passed. It is a "
                   "reminder that has already fired.",
        "action": "act on it, then kb.py set <name> due YYYY-MM-DD (or kb.py rm <name>)",
    },
    {
        "key": "stale",
        "label": "Stale",
        "meaning": f"Not re-checked in over {STALE_DAYS} days. It may still be "
                   "true; nobody has looked.",
        "action": "re-check it against the source, then kb.py verify <name>",
    },
    {
        "key": "unverified",
        "label": "Unverified",
        "meaning": "Recorded but never confirmed against a primary source. "
                   "Treat as a claim, not a fact.",
        "action": "confirm it, then kb.py verify <name> --confidence verified",
    },
    {
        "key": "provisional",
        "label": "Provisional",
        "meaning": "Confidence is low or medium — believed, but the evidence "
                   "was indirect.",
        "action": "check it directly, then kb.py verify <name> --confidence verified",
    },
    {
        "key": "isolated",
        "label": "Isolated",
        "meaning": "Nothing links to it, or it links to nothing. It will not "
                   "be found by following the graph.",
        "action": "kb.py link <other-entry> <name>",
    },
    {
        "key": "ageing",
        "label": "Ageing",
        "meaning": "Still fresh, but approaching the staleness cutoff. "
                   "Nothing is wrong yet.",
        "action": "nothing now; re-verify before the review date",
    },
    {
        "key": "current",
        "label": "Current",
        "meaning": "Verified recently, trusted, and connected to the graph. "
                   "Nothing to do.",
        "action": "nothing; re-verify by the review date to keep it here",
    },
    {
        "key": "archived",
        "label": "Archived",
        "meaning": "Retired from retrieval on purpose. Still readable and "
                   "still in the graph; it just no longer answers queries.",
        "action": "nothing; kb.py archive <name> --undo puts it back",
    },
]
STATUS_BY_KEY = {s["key"]: s for s in STATUS_MODEL}
STATUS_ORDER = [s["key"] for s in STATUS_MODEL]

# Which triage reason code implies which status.
_REASON_STATUS = {
    "invalid-due": "broken",
    "invalid-date": "broken",
    "overdue": "overdue",
    "stale": "stale",
    "unverified": "unverified",
    "never-verified": "unverified",
    "orphan": "isolated",
    "unlinked": "isolated",
}

# --- Ranked retrieval -------------------------------------------------------
# Classic BM25 over the whole store. The corpus is a few dozen files, so
# scoring every entry on every query costs nothing and needs no index.
BM25_K1 = 1.5
BM25_B = 0.75
# A term in the name says more about what an entry is about than the same term
# buried in the body. Weighting is applied by repeating the field's tokens.
FIELD_WEIGHTS = {"name": 3, "description": 2, "body": 1, "meta": 1}
# Type-aware scoring. Some memory types are simply better answers to a
# "what do I need to know" query than others.
TYPE_WEIGHTS = {
    "semantic": 1.0,
    "procedural": 1.0,
    "retrieval": 1.0,
    "prospective": 0.9,
    "episodic": 0.85,
    "parametric": 0.6,
    "working": 0.4,
}
# Episodic memory is a log: a recent run is far more informative than an old
# one, so recency is a first-class signal for that type only.
EPISODIC_HALF_LIFE_DAYS = 90
EPISODIC_RECENCY_WEIGHT = 0.4
# Trust nudges the ranking without ever letting confidence outrank relevance.
CONFIDENCE_WEIGHTS = {
    "verified": 1.10,
    "high": 1.05,
    "medium": 1.0,
    "low": 0.92,
    "unverified": 0.88,
}
# Rough characters-per-token, good enough to hold a context pack to a budget
# without pulling in a tokenizer.
CHARS_PER_TOKEN = 4
DEFAULT_CONTEXT_BUDGET = 2000
_WORD = re.compile(r"[a-z0-9][a-z0-9_.-]*")


def tokenize(text):
    """Lowercase word tokens, dropping single characters and pure noise."""
    return [t.strip(".-_") for t in _WORD.findall(str(text).lower())
            if len(t.strip(".-_")) > 1]


def is_archived(fm):
    """Archived entries stay on disk and in the graph, but leave retrieval."""
    return bool(fm.get("archived"))


# --- Near-verbatim duplicate detection --------------------------------------
# Word shingles plus Jaccard, the classic Broder construction. Deliberately
# *not* MinHash/LSH: those approximate Jaccard to make O(n^2) tractable at web
# scale, and this store is a few dozen files, where the exact computation is
# free and an approximation would only add error.
#
# What this catches is near-verbatim overlap — the same text recorded twice.
# What it does not catch is two entries making the same claim in different
# words, which was measured rather than assumed: a hand-written paraphrase of
# an existing entry scored below thirteen pairs of merely-related entries on
# this corpus. See [[kb-duplicate-detection-limits]] before raising the
# sensitivity to "find more" — the next thing found will be a false positive.
SHINGLE_K = 5
DUPES_THRESHOLD = 0.5
# Below this, a document has too few shingles for the score to mean anything;
# the estimate's error swamps the signal on very short texts.
MIN_SHINGLES = 20


def shingles(text, k=SHINGLE_K):
    """Overlapping k-word sequences — the unit near-duplicate detection uses."""
    toks = tokenize(text)
    if len(toks) < k:
        return set()
    return {" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1)}


def dupe_pairs(threshold=DUPES_THRESHOLD):
    """Entry pairs whose text overlaps near-verbatim, most similar first.

    Reports two numbers because they answer different questions. *Jaccard* is
    symmetric and asks "are these the same entry twice". *Containment* is
    asymmetric and asks "is the smaller one already wholly inside the larger" —
    the case where one entry has been superseded rather than duplicated, which
    Jaccard scores low precisely when the sizes differ most.

    Returns (pairs, skipped) — skipped entries were too short to judge.
    """
    docs, skipped = [], []
    for t, path in iter_entries():
        try:
            fm, body = parse_frontmatter(path)
        except OSError:
            continue
        name = fm.get("name", path.stem)
        s = shingles(f"{fm.get('description', '')} {body}")
        if len(s) < MIN_SHINGLES:
            skipped.append(name)
            continue
        docs.append((name, t, fm, s))

    pairs = []
    for i, (n1, t1, fm1, s1) in enumerate(docs):
        for n2, t2, fm2, s2 in docs[i + 1:]:
            inter = len(s1 & s2)
            if not inter:
                continue
            jaccard = inter / len(s1 | s2)
            containment = inter / min(len(s1), len(s2))
            if jaccard < threshold and containment < threshold:
                continue
            linked = n2 in (fm1.get("links") or []) or n1 in (fm2.get("links") or [])
            pairs.append({
                "a": n1, "b": n2, "a_type": t1, "b_type": t2,
                "jaccard": round(jaccard, 3),
                "containment": round(containment, 3),
                "shared_shingles": inter,
                "linked": linked,
            })
    pairs.sort(key=lambda p: (-max(p["jaccard"], p["containment"]), p["a"], p["b"]))
    return pairs, skipped


# --- Semantic duplicate candidates: blocking, not deciding ------------------
# `dupe_pairs` above answers "is this text recorded twice", and can answer it
# alone. The harder question — do these two entries make the *same claim in
# different words* — no lexical metric can answer, which was measured rather
# than assumed: see [[kb-duplicate-detection-limits]].
#
# What was measured since is that the failure was in the framing, not in the
# metric. A global threshold asks "is this pair similar in absolute terms", and
# absolute similarity is dominated by how much vocabulary a *topic* happens to
# share — which varies far more between topics than duplication does within
# one. Asking instead "of everything here, which entries is this one MOST
# like" cancels that per-entry baseline out. Over seven hand-written
# paraphrases planted in this store: ranked globally, the worst of them sat at
# #81 of 378 pairs; taken as each entry's single nearest neighbour, unioned in
# both directions, all seven were caught inside 19 pairs — 5% of the space.
#
# So what follows is a *blocker*: the cheap, recall-oriented half of the
# standard record-linkage pair. It narrows the pair space to a few dozen and
# then stops, because deciding is a judgement someone makes by reading both
# entries. `record_verdict` is where that judgement is written down.
NEIGHBOURS = 3
# Below this an entry has too few distinct words for overlap to mean anything.
MIN_CANDIDATE_TOKENS = 20
VERDICTS = ("duplicate", "overlap", "distinct")
VERDICTS_FILE = KB_DIR / "verdicts.json"


def _claim_text(fm, body):
    """The part of an entry that carries its claim, and nothing else."""
    return f"{fm.get('description', '')} {body}"


def content_digest(fm, body):
    """Fingerprint of the text a verdict was passed on.

    Over description and body only, deliberately. Re-verifying an entry or
    linking it elsewhere does not change what it *claims*, so it must not
    expire a judgement about what it claims.
    """
    return hashlib.sha256(_claim_text(fm, body).encode("utf-8")).hexdigest()[:12]


def _candidate_docs():
    """Live entries with their token sets. Archived ones are already retired."""
    docs, skipped = [], []
    for t, path in iter_entries():
        try:
            fm, body = parse_frontmatter(path)
        except OSError:
            continue
        if is_archived(fm):
            continue
        name = fm.get("name", path.stem)
        tokens = set(tokenize(_claim_text(fm, body)))
        if len(tokens) < MIN_CANDIDATE_TOKENS:
            skipped.append(name)
            continue
        docs.append({"name": name, "type": t, "fm": fm, "body": body,
                     "tokens": tokens})
    return docs, skipped


def neighbour_pairs(neighbours=NEIGHBOURS, docs=None):
    """Each entry's most-similar others by token overlap, unioned both ways.

    The union matters and is not a detail: a long entry's nearest neighbour is
    often not the short entry that restates it, while the short one's nearest
    neighbour is reliably the long one. Taking the pair if *either* side
    nominates it — rather than requiring both — is what turned 6 of 7 planted
    paraphrases into 7 of 7 at no extra cost.

    Token-set Jaccard, not shingles: shingles measure shared *phrasing*, which
    is exactly what a restatement does not share.

    Returns (pairs, skipped), most similar first.
    """
    skipped = []
    if docs is None:
        docs, skipped = _candidate_docs()
    sims = {}
    for i, a in enumerate(docs):
        for j in range(i + 1, len(docs)):
            b = docs[j]
            shared = len(a["tokens"] & b["tokens"])
            if not shared:
                continue
            sims[(i, j)] = (shared / len(a["tokens"] | b["tokens"]), shared)

    adjacent = collections.defaultdict(list)
    for (i, j), (score, shared) in sims.items():
        adjacent[i].append((score, j))
        adjacent[j].append((score, i))

    keep = set()
    for i, neighbourhood in adjacent.items():
        neighbourhood.sort(key=lambda t: (-t[0], docs[t[1]]["name"]))
        for _, j in neighbourhood[:max(neighbours, 0)]:
            keep.add((min(i, j), max(i, j)))

    pairs = []
    for i, j in keep:
        a, b = docs[i], docs[j]
        score, shared = sims[(i, j)]
        pairs.append({
            "a": a["name"], "b": b["name"],
            "a_type": a["type"], "b_type": b["type"],
            "a_description": a["fm"].get("description", ""),
            "b_description": b["fm"].get("description", ""),
            "similarity": round(score, 3),
            "shared_tokens": shared,
            "linked": (b["name"] in (a["fm"].get("links") or [])
                       or a["name"] in (b["fm"].get("links") or [])),
        })
    pairs.sort(key=lambda p: (-p["similarity"], p["a"], p["b"]))
    return pairs, skipped


def _verdict_key(a, b):
    """Order-independent identity for a pair."""
    return " :: ".join(sorted((a, b)))


def load_verdicts():
    """Standing judgements, keyed by pair. Missing file means none yet."""
    if not VERDICTS_FILE.is_file():
        return {}
    try:
        data = json.loads(VERDICTS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"warning: ignoring unreadable {VERDICTS_FILE.name}: {e}",
              file=sys.stderr)
        return {}
    return {_verdict_key(v["a"], v["b"]): v
            for v in data.get("verdicts", [])
            if isinstance(v, dict) and v.get("a") and v.get("b")}


def save_verdicts(verdicts):
    VERDICTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1,
               "verdicts": [verdicts[k] for k in sorted(verdicts)]}
    VERDICTS_FILE.write_text(json.dumps(payload, indent=2) + "\n",
                             encoding="utf-8")


def record_verdict(a_name, a_fm, a_body, b_name, b_fm, b_body, verdict, note=""):
    """Write down a judgement about one pair, against the text it was made on."""
    verdicts = load_verdicts()
    a, b = sorted(((a_name, a_fm, a_body), (b_name, b_fm, b_body)),
                  key=lambda e: e[0])
    verdicts[_verdict_key(a_name, b_name)] = {
        "a": a[0], "b": b[0],
        "verdict": verdict,
        "judged": datetime.date.today().isoformat(),
        "a_digest": content_digest(a[1], a[2]),
        "b_digest": content_digest(b[1], b[2]),
        "note": note or "",
    }
    save_verdicts(verdicts)


def candidate_pairs(neighbours=NEIGHBOURS, include_judged=False):
    """Pairs worth judging, with any standing verdict attached.

    A verdict is bound to the content it was passed on. If either entry has
    been rewritten since, the pair returns marked `verdict_stale` and is
    surfaced again — a judgement about text that no longer exists is not a
    judgement.

    Settled pairs drop out of the default view, with one exception: a pair
    judged `duplicate` stays until somebody actually merges it. That is
    outstanding work, not a closed question.

    Returns (pairs, skipped).
    """
    docs, skipped = _candidate_docs()
    pairs, _ = neighbour_pairs(neighbours=neighbours, docs=docs)
    digests = {d["name"]: content_digest(d["fm"], d["body"]) for d in docs}
    verdicts = load_verdicts()

    out = []
    for p in pairs:
        v = verdicts.get(_verdict_key(p["a"], p["b"]))
        p["verdict"] = v.get("verdict") if v else None
        p["judged"] = v.get("judged", "") if v else ""
        p["note"] = v.get("note", "") if v else ""
        p["verdict_stale"] = bool(v) and not (
            v.get("a_digest") == digests.get(v.get("a"))
            and v.get("b_digest") == digests.get(v.get("b")))
        settled = (v and not p["verdict_stale"]
                   and p["verdict"] in ("distinct", "overlap"))
        if settled and not include_judged:
            continue
        out.append(p)
    return out, skipped


def effective_confidence(fm, today=None):
    """Stored confidence demoted one level per staleness period elapsed.

    `confidence` records how well a fact was checked *when it was checked*.
    On its own it says nothing about how long ago that was, so an entry can
    sit at `verified` forever while nobody looks at it — which is exactly the
    failure this store is supposed to avoid. Ranking therefore uses a decayed
    level: a `verified` fact untouched for a year is not verified.

    Nothing here rewrites the file. Decay is applied at read time and undone
    by `kb.py verify`, so the recorded claim stays exactly as its author wrote
    it and the ageing is never a silent edit.

    Returns (level, steps_demoted).
    """
    stored = fm.get("confidence", "")
    if stored not in CONFIDENCE_LEVELS:
        return stored, 0
    today = today or datetime.date.today()
    for key in ("last_verified", "created"):
        value = fm.get(key)
        if not value:
            continue
        try:
            age = (today - datetime.date.fromisoformat(str(value))).days
        except ValueError:
            continue
        steps = max(age, 0) // STALE_DAYS
        if not steps:
            return stored, 0
        start = CONFIDENCE_LEVELS.index(stored)
        end = min(start + steps, len(CONFIDENCE_LEVELS) - 1)
        return CONFIDENCE_LEVELS[end], end - start
    return stored, 0


def entry_documents():
    """Every entry as (type, path, frontmatter, body, weighted token list)."""
    docs = []
    for t, path in iter_entries():
        try:
            fm, body = parse_frontmatter(path)
        except OSError as e:
            print(f"warning: skipping {path.relative_to(ROOT)}: {e}", file=sys.stderr)
            continue
        meta = " ".join(
            serialize_value(v) for k, v in fm.items()
            if k not in ("name", "description")
        )
        fields = {
            "name": fm.get("name", path.stem).replace("-", " "),
            "description": fm.get("description", ""),
            "body": body,
            "meta": meta,
        }
        tokens = []
        for field, weight in FIELD_WEIGHTS.items():
            tokens += tokenize(fields[field]) * weight
        docs.append((t, path, fm, body, tokens))
    return docs


def _recency_factor(fm, today):
    """Episodic recency multiplier: 1 + w at today, decaying to 1 over time."""
    for key in ("last_verified", "created"):
        value = fm.get(key)
        if not value:
            continue
        try:
            age = (today - datetime.date.fromisoformat(str(value))).days
        except ValueError:
            continue
        age = max(age, 0)
        return 1 + EPISODIC_RECENCY_WEIGHT * 0.5 ** (age / EPISODIC_HALF_LIFE_DAYS)
    return 1.0


def rank(query, types=None, include_episodic=True, docs=None,
         include_archived=False):
    """Score every entry against a query with BM25 plus type-aware weighting.

    BM25 supplies relevance. On top of it, three signals that are specific to
    a memory store: the memory *type* (a procedure answers a task better than
    a working-memory scratch file), *recency* for episodic entries only
    (a log entry decays in usefulness, a fact does not), and *confidence*
    (a nudge — it can reorder near-ties, never outrank a real match).

    Confidence enters as its *aged* value, not the value on disk, so an entry
    nobody has re-checked in a year stops competing as though it were fresh.
    Archived entries are out of the retrieval set entirely — that is what
    archiving means — but remain readable and remain in the graph.

    Returns hits scoring above zero, best first.
    """
    q = tokenize(query)
    docs = entry_documents() if docs is None else docs
    if not q or not docs:
        return []

    n = len(docs)
    avgdl = sum(len(d[4]) for d in docs) / n
    df = collections.Counter()
    counts = []
    for _, _, _, _, tokens in docs:
        c = collections.Counter(tokens)
        counts.append(c)
        for term in set(q):
            if c[term]:
                df[term] += 1

    today = datetime.date.today()
    hits = []
    for (t, path, fm, body, tokens), c in zip(docs, counts):
        if types and t not in types:
            continue
        if not include_episodic and t == "episodic":
            continue
        if not include_archived and is_archived(fm):
            continue
        dl = len(tokens) or 1
        base = 0.0
        matched = []
        for term in q:
            f = c[term]
            if not f:
                continue
            matched.append(term)
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            base += idf * (f * (BM25_K1 + 1)) / (
                f + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl)
            )
        if base <= 0:
            continue
        effective, decayed_by = effective_confidence(fm, today)
        score = base * TYPE_WEIGHTS.get(t, 1.0)
        score *= CONFIDENCE_WEIGHTS.get(effective, 1.0)
        if t == "episodic":
            score *= _recency_factor(fm, today)
        hits.append({
            "name": fm.get("name", path.stem),
            "type": t,
            "path": str(path.relative_to(ROOT)),
            "description": fm.get("description", ""),
            "confidence": fm.get("confidence", ""),
            "effective_confidence": effective,
            "decayed_by": decayed_by,
            "archived": fm.get("archived", ""),
            "last_verified": fm.get("last_verified", ""),
            "score": round(score, 3),
            "bm25": round(base, 3),
            "matched": sorted(set(matched)),
            "snippet": snippet(body, set(q)),
            "body": body,
        })
    hits.sort(key=lambda h: (-h["score"], h["name"]))
    return hits


def snippet(body, terms, width=160):
    """The first line of the body that mentions a query term."""
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("---", "|", "#")):
            continue
        if terms & set(tokenize(stripped)):
            return stripped[:width] + ("…" if len(stripped) > width else "")
    for line in body.splitlines():
        if line.strip():
            return line.strip()[:width]
    return ""


def est_tokens(text):
    """Cheap token estimate — no tokenizer, no dependency."""
    return max(1, -(-len(text) // CHARS_PER_TOKEN))


def context_pack(query, budget=DEFAULT_CONTEXT_BUDGET, types=None,
                 include_episodic=False, limit=None):
    """A paste-ready, budgeted brief on a task, with provenance per entry.

    Entries go in best-first until the budget is spent; the one that straddles
    the boundary is trimmed at a paragraph break rather than dropped, so the
    pack always uses the budget it was given. Episodic logs are left out by
    default: they describe one past run, which usually crowds out the durable
    knowledge a task actually needs.
    """
    hits = rank(query, types=types, include_episodic=include_episodic)
    if limit:
        hits = hits[:limit]

    sections, used, included, trimmed = [], 0, [], []
    for hit in hits:
        # An aged entry reports both numbers: what its author claimed, and
        # what that claim is worth now. Hiding either would be the kind of
        # unattributed context this pack exists to prevent.
        confidence = hit["confidence"] or "unknown"
        if hit.get("decayed_by"):
            confidence = f"{hit['effective_confidence']} (recorded as {hit['confidence']}, aged)"
        header = (
            f"### {hit['name']}  ({hit['type']})\n"
            f"> {hit['description']}\n"
            f"> confidence: {confidence} · "
            f"last verified: {hit['last_verified'] or 'never'} · "
            f"source: {hit['path']} · relevance: {hit['score']}\n\n"
        )
        remaining = budget - used - est_tokens(header)
        if remaining <= 0:
            break
        body = hit["body"].strip()
        if est_tokens(body) > remaining:
            body = _trim_to_tokens(body, remaining)
            if not body:
                break
            trimmed.append(hit["name"])
        sections.append(header + body + "\n")
        used += est_tokens(header) + est_tokens(body)
        included.append(hit)

    head = (
        f"# Context for: {query}\n\n"
        f"{len(included)} entr{'y' if len(included) == 1 else 'ies'} from the "
        f"knowledge base, most relevant first, ~{used} tokens "
        f"(budget {budget}).\n\n"
    )
    return {
        "query": query,
        "budget": budget,
        "tokens": used,
        "entries": [{k: v for k, v in h.items() if k != "body"} for h in included],
        "trimmed": trimmed,
        "text": head + "\n".join(sections) if sections else head + "(no matches)\n",
    }


TRIM_MARKER = "\n\n_(trimmed to fit the context budget)_"


def _trim_to_tokens(body, budget):
    """Cut a body to a token budget at the last paragraph break that fits.

    The "trimmed" marker is charged against the same budget, so a pack never
    overshoots the number it was given.
    """
    limit = budget * CHARS_PER_TOKEN - len(TRIM_MARKER)
    if limit <= 0:
        return ""
    head = body[:limit]
    cut = head.rfind("\n\n")
    if cut > limit // 3:
        head = head[:cut]
    return head.rstrip() + TRIM_MARKER



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
        # Archiving is the decision that an entry no longer needs attention.
        # Continuing to flag it as stale would make the queue un-clearable.
        if is_archived(fm):
            continue
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


def status_report():
    """Every entry with the one status that describes it, worst first.

    Triage answers "what is broken"; this answers "where does each entry
    stand, and what single command moves it". Same rules, no gaps: every
    entry appears exactly once.
    """
    today = datetime.date.today()
    by_name = {r["name"]: r for r in triage_report()}

    report = []
    for t, path in iter_entries():
        try:
            fm, _ = parse_frontmatter(path)
        except OSError:
            continue
        name = fm.get("name", path.stem)
        confidence = fm.get("confidence", "")
        reasons = [x for x in by_name.get(name, {}).get("reasons", [])]

        age = review = None
        lv = fm.get("last_verified")
        if lv:
            try:
                d = datetime.date.fromisoformat(lv)
                age = (today - d).days
                review = (d + datetime.timedelta(days=STALE_DAYS)).isoformat()
            except ValueError:
                pass

        effective, decayed_by = effective_confidence(fm, today)
        candidates = {_REASON_STATUS[x["code"]] for x in reasons
                      if x["code"] in _REASON_STATUS}
        if confidence in ("low", "medium"):
            candidates.add("provisional")
        if not candidates and age is not None and age > STALE_DAYS * AGEING_RATIO:
            candidates.add("ageing")
        if is_archived(fm):
            status = "archived"
        else:
            status = min(candidates, key=STATUS_ORDER.index) if candidates else "current"

        report.append({
            "name": name,
            "type": t,
            "path": str(path.relative_to(ROOT)),
            "confidence": confidence,
            "effective_confidence": effective,
            "decayed_by": decayed_by,
            "archived": fm.get("archived", ""),
            "description": fm.get("description", ""),
            "status": status,
            "label": STATUS_BY_KEY[status]["label"],
            "action": STATUS_BY_KEY[status]["action"].replace("<name>", name),
            "last_verified": lv or "",
            "age_days": age,
            "review_by": review or "",
            "reasons": reasons,
        })

    report.sort(key=lambda r: (STATUS_ORDER.index(r["status"]), r["type"], r["name"]))
    return report


def cmd_status(args):
    report = status_report()
    if args.type:
        report = [r for r in report if r["type"] == args.type]
    if args.status:
        report = [r for r in report if r["status"] == args.status]
    if args.json:
        print(json.dumps(report, indent=2))
        return
    if args.legend:
        print("Entry statuses, worst first. Each is left by running its action.\n")
        for s in STATUS_MODEL:
            print(f"{s['label']} ({s['key']})")
            print(f"  {s['meaning']}")
            print(f"  → {s['action']}\n")
        return
    if not report:
        print("no entries match")
        return

    counts = collections.Counter(r["status"] for r in report)
    for key in STATUS_ORDER:
        rows = [r for r in report if r["status"] == key]
        if not rows:
            continue
        s = STATUS_BY_KEY[key]
        print(f"\n{s['label'].upper()} ({len(rows)}) — {s['meaning']}")
        print(f"  action: {s['action']}")
        for r in rows:
            age = f"{r['age_days']}d ago" if r["age_days"] is not None else "never"
            conf = r["confidence"]
            if r["decayed_by"]:
                conf = f"{r['effective_confidence']}<-{r['confidence']}"
            print(f"    [{r['type']:11}] {r['name']:34} {conf:22} verified {age}")

    summary = "  ".join(f"{STATUS_BY_KEY[k]['label'].lower()}: {counts[k]}"
                        for k in STATUS_ORDER if counts[k])
    print(f"\n{len(report)} entries — {summary}")
    print("Run 'kb.py status --legend' for what each status means.")


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


def cmd_dupes(args):
    pairs, skipped = dupe_pairs(threshold=args.threshold)
    if args.json:
        print(json.dumps({"threshold": args.threshold, "pairs": pairs,
                          "too_short": skipped}, indent=2))
        return
    if not pairs:
        print(f"no near-duplicate pairs above {args.threshold}")
    for p in pairs:
        flag = " (already linked)" if p["linked"] else ""
        print(f"{max(p['jaccard'], p['containment']):.2f}  "
              f"{p['a']} <-> {p['b']}{flag}")
        print(f"      jaccard {p['jaccard']}  containment {p['containment']}  "
              f"({p['shared_shingles']} shared {SHINGLE_K}-word sequences)")
    if pairs:
        print(f"\n{len(pairs)} pair(s) above {args.threshold} — read both, then "
              f"merge by hand and 'kb.py archive' the loser.")
    if skipped:
        print(f"\n{len(skipped)} entr(ies) too short to compare "
              f"(<{MIN_SHINGLES} shingles): {', '.join(sorted(skipped))}")
    print("\nThis finds text recorded twice, not the same claim written twice —"
          "\nsee the 'kb-duplicate-detection-limits' entry for why."
          "\nFor the same claim in different words, run 'kb.py candidates'.")


CANDIDATES_CAVEAT = (
    "These are candidates, not duplicates. This is the recall half of the "
    "job:\nabout one pair in three to eight is a real restatement, and no "
    "score here can\ntell you which. Read both entries, then record the call."
)


def cmd_candidates(args):
    pairs, skipped = candidate_pairs(neighbours=args.neighbours,
                                     include_judged=args.all)
    if args.json:
        print(json.dumps({"neighbours": args.neighbours, "pairs": pairs,
                          "too_short": skipped}, indent=2))
        return
    if not pairs:
        print(f"no unjudged candidate pairs at {args.neighbours} neighbour(s) per entry")
    for p in pairs:
        tags = []
        if p["linked"]:
            tags.append("already linked")
        if p["verdict"]:
            tags.append(f"judged {p['verdict']} {p['judged']}"
                        + (" — TEXT CHANGED SINCE" if p["verdict_stale"] else ""))
        suffix = f"  ({'; '.join(tags)})" if tags else ""
        print(f"\n{p['similarity']:.2f}  {p['a']} <-> {p['b']}{suffix}")
        print(f"      {p['a_type']}/{p['b_type']}, {p['shared_tokens']} shared words")
        print(f"      a: {p['a_description']}")
        print(f"      b: {p['b_description']}")
        if p["note"]:
            print(f"      note: {p['note']}")
    if pairs:
        print(f"\n{len(pairs)} pair(s) to judge. {CANDIDATES_CAVEAT}\n"
              f"  kb.py judge <a> <b> {'|'.join(VERDICTS)} [--note ...]")
    if skipped:
        print(f"\n{len(skipped)} entr(ies) too short to compare "
              f"(<{MIN_CANDIDATE_TOKENS} distinct words): {', '.join(sorted(skipped))}")


def cmd_judge(args):
    a_type, a_path, a_fm, a_body = _require(args.a)
    b_type, b_path, b_fm, b_body = _require(args.b)
    a_name = a_fm.get("name", a_path.stem)
    b_name = b_fm.get("name", b_path.stem)
    if a_name == b_name:
        print("an entry cannot duplicate itself", file=sys.stderr)
        sys.exit(1)
    record_verdict(a_name, a_fm, a_body, b_name, b_fm, b_body,
                   args.verdict, args.note or "")
    # No entry in .kb/log.md: that log tracks changes to entries, and a verdict
    # changes none. The ledger is its own record and is git-tracked.
    print(f"recorded: {a_name} <-> {b_name} = {args.verdict}")
    follow_up = {
        "duplicate": "merge the two by hand, then 'kb.py archive' the loser — "
                     "this pair stays in 'candidates' until you do",
        "overlap": "related but both earn their place; "
                   f"'kb.py link {a_name} {b_name}' if they are not linked yet",
        "distinct": "this pair will stay out of 'candidates' unless either "
                    "entry's text changes",
    }
    print(f"next: {follow_up[args.verdict]}")


def cmd_archive(args):
    """Retire an entry from retrieval without destroying it.

    Deletion loses the audit trail: you can no longer see that a thing was
    once believed, or what linked to it. Archiving keeps the file, the links,
    and the graph position, and only takes the entry out of the set that
    answers queries. `rm` is still there when the entry should genuinely go.
    """
    t, path, fm, _ = _require(args.name)
    today = datetime.date.today().isoformat()
    rel = path.relative_to(ROOT)

    if args.undo:
        if not is_archived(fm):
            print(f"'{args.name}' is not archived", file=sys.stderr)
            sys.exit(1)
        write_frontmatter(path, {"archived": None})
        _append_log(t, path.stem, today, "unarchived")
        print(f"unarchived {rel} — back in the retrieval set")
        return

    if is_archived(fm):
        print(f"'{args.name}' is already archived (since {fm['archived']})")
        return
    write_frontmatter(path, {"archived": today})
    _append_log(t, path.stem, today, "archived")
    print(f"archived {rel} — out of the retrieval set, still readable and still linked")


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
    hits = rank(args.query, types=[args.type] if args.type else None,
                include_archived=args.archived)
    if args.json:
        payload = [{k: v for k, v in h.items() if k != "body"} for h in hits]
        print(json.dumps(payload[: args.limit] if args.limit else payload, indent=2))
        return
    if not hits:
        print("(no matches)")
        return
    shown = hits[: args.limit] if args.limit else hits
    for i, h in enumerate(shown, 1):
        flags = ""
        if h["archived"]:
            flags += "  [archived]"
        if h["decayed_by"]:
            flags += f"  [{h['confidence']} -> {h['effective_confidence']}, aged]"
        print(f"{i:2}. {h['score']:6.2f}  [{h['type']:11}] {h['name']}{flags}")
        if h["description"]:
            print(f"           {h['description']}")
        if h["snippet"]:
            print(f"           … {h['snippet']}")
        print(f"           {h['path']}  ({', '.join(h['matched'])})")
    if len(hits) > len(shown):
        print(f"\n{len(hits) - len(shown)} more — raise --limit to see them.")


def cmd_context(args):
    pack = context_pack(
        args.query,
        budget=args.budget,
        types=[args.type] if args.type else None,
        include_episodic=args.episodic,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(pack, indent=2))
        return
    print(pack["text"])


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
    archived_names = set()
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

        archived = fm.get("archived")
        if archived:
            archived_names.add(name)
            try:
                datetime.date.fromisoformat(str(archived))
            except ValueError:
                problems.append(f"{rel}: archived is not a valid date: {archived!r}")

        lv = fm.get("last_verified")
        if lv:
            try:
                lv_date = datetime.date.fromisoformat(lv)
                age = (today - lv_date).days
                # Freshness warnings are noise on an entry that was retired on
                # purpose — archiving already answered "what about this one".
                if age > STALE_DAYS and not archived:
                    warnings.append(f"{rel}: stale, last_verified {age}d ago (>{STALE_DAYS}d)")
                if confidence == "unverified" and age > UNVERIFIED_DAYS and not archived:
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
        if name not in inbound and name not in archived_names:
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

    p_search = sub.add_parser("search", help="ranked search across all entries")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10,
                          help="how many hits to show (0 for all; default 10)")
    p_search.add_argument("--type", choices=TYPES, help="only this memory type")
    p_search.add_argument("--archived", action="store_true",
                          help="also search archived entries, excluded by default")
    p_search.add_argument("--json", action="store_true", help="machine-readable output")
    p_search.set_defaults(func=cmd_search)

    p_context = sub.add_parser(
        "context", help="paste-ready, budgeted context pack for a task")
    p_context.add_argument("query", help="the task you are about to work on")
    p_context.add_argument("--budget", type=int, default=DEFAULT_CONTEXT_BUDGET,
                           help=f"approximate token budget (default {DEFAULT_CONTEXT_BUDGET})")
    p_context.add_argument("--limit", type=int, default=0,
                           help="cap the number of entries considered (0 for no cap)")
    p_context.add_argument("--type", choices=TYPES, help="only this memory type")
    p_context.add_argument("--episodic", action="store_true",
                           help="include episodic logs, excluded by default")
    p_context.add_argument("--json", action="store_true", help="machine-readable output")
    p_context.set_defaults(func=cmd_context)

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

    p_status = sub.add_parser("status",
                              help="where every entry stands, and the command that moves it")
    p_status.add_argument("--type", choices=TYPES, help="only this memory type")
    p_status.add_argument("--status", choices=STATUS_ORDER, help="only entries in this status")
    p_status.add_argument("--legend", action="store_true",
                          help="explain each status and how to leave it")
    p_status.add_argument("--json", action="store_true", help="machine-readable output")
    p_status.set_defaults(func=cmd_status)

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

    p_dupes = sub.add_parser(
        "dupes", help="entry pairs whose text overlaps near-verbatim")
    p_dupes.add_argument("--threshold", type=float, default=DUPES_THRESHOLD,
                         help=f"minimum jaccard or containment (default {DUPES_THRESHOLD})")
    p_dupes.add_argument("--json", action="store_true", help="machine-readable output")
    p_dupes.set_defaults(func=cmd_dupes)

    p_cand = sub.add_parser(
        "candidates",
        help="pairs that may make the same claim in different words — for an agent to judge")
    p_cand.add_argument("-n", "--neighbours", type=int, default=NEIGHBOURS,
                        help=f"nearest neighbours per entry (default {NEIGHBOURS}); "
                             "higher trades more pairs to read for more recall")
    p_cand.add_argument("--all", action="store_true",
                        help="include pairs already judged distinct or overlapping")
    p_cand.add_argument("--json", action="store_true", help="machine-readable output")
    p_cand.set_defaults(func=cmd_candidates)

    p_judge = sub.add_parser(
        "judge", help="record a judgement about one candidate pair")
    p_judge.add_argument("a")
    p_judge.add_argument("b")
    p_judge.add_argument("verdict", choices=VERDICTS)
    p_judge.add_argument("--note", help="one line on why, kept with the verdict")
    p_judge.set_defaults(func=cmd_judge)

    p_archive = sub.add_parser(
        "archive", help="retire an entry from retrieval without deleting it")
    p_archive.add_argument("name")
    p_archive.add_argument("--undo", action="store_true",
                           help="put an archived entry back in the retrieval set")
    p_archive.set_defaults(func=cmd_archive)

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
