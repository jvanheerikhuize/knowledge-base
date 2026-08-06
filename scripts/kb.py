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
import subprocess
import sys
import textwrap

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
    # Worse than broken metadata: a broken date means one entry escapes a
    # check, a standing contradiction means the store answers a question two
    # incompatible ways and one of the answers is wrong.
    "contradiction": -1,
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
# A store written in one burst comes due in one burst. When every live entry's
# review date falls inside this fraction of the review cycle, the store is one
# cohort rather than a spread, and `triage` reads clean right up to the day all
# of it goes stale together. Below the entry floor the narrowness is arithmetic
# rather than a finding — three entries cannot help but be concentrated.
COHORT_RATIO = 1 / 3
COHORT_MIN_ENTRIES = 5

# Every entry sits in exactly one of these states. Ordered worst first: an
# entry that qualifies for several takes the earliest one, so the status
# answers "what is the single next thing to do about this entry".
# `action` is the literal command that moves it out of the state.
STATUS_MODEL = [
    {
        "key": "contradicted",
        "label": "Contradicted",
        "meaning": "Another entry has been judged to disagree with this one. "
                   "Whatever else is true, one of them is wrong.",
        "action": "reconcile the two, then re-judge the pair with "
                  "kb.py judge <a> <b> <verdict> --agreement agree",
    },
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
    "contradiction": "contradicted",
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
        if is_archived(fm):
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

# --- The second question: do these two entries disagree? --------------------
# Contradiction is a *separate axis* from duplication, not a fourth value of
# it, and that was measured rather than assumed. Nine contradictions (eight
# hand-written, one recovered from this repo's own git history) were planted
# in a copy of the store and every cheap signal was scored against them:
#
#   global topical similarity   contradicting pairs land anywhere from #2 to
#                               #107 of 435 — the same failure a global
#                               threshold has for duplicates
#   claim-level alignment       a tight net (2% of the pair space) but only
#                               4 of 9 — sentences are short, and two entries
#                               rarely word the same claim the same way
#   negation-polarity mismatch  5 of 9, and it cannot see the commonest shape
#                               of all: two competing *positive* assertions
#                               ("20 repos" against "22 repos"). Its false
#                               positives are negation-scope errors ("this is
#                               not just a preference") and entries that agree
#                               *about* a contradiction elsewhere
#
# So no cheap signal decides it, and — the useful half — none is needed. The
# nearest-neighbour blocker built for duplicates already caught 8 of the 9 at
# its default setting and 9 of 9 at `-n 5`. What was missing was never a
# detector; it was that `duplicate|overlap|distinct` has no way to say "these
# two disagree", so a pair could be judged, look settled, and never have been
# asked. Hence a second field on the same verdict.
#
# The two axes really are independent: of the pairs this store has judged, the
# contradicting ones are spread across `overlap` and `distinct` alike, and a
# pair can restate *and* disagree (an entry corrected in place against the one
# that corrected it). Absent means unexamined, and is reported as such —
# silence must not read as "checked, they agree".
AGREEMENTS = ("agree", "contradict")


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


def record_verdict(a_name, a_fm, a_body, b_name, b_fm, b_body, verdict,
                   note=None, agreement=None):
    """Write down a judgement about one pair, against the text it was made on.

    `agreement` is the second, independent axis: `agree`, `contradict`, or
    None for "nobody has looked". None is stored as an absent key rather than
    a value, so a ledger written before the axis existed reads correctly as
    unexamined instead of quietly as "fine".

    `note=None` means "say nothing about the note" and keeps whatever the
    pair already carried. Adding the agreement axis re-opened every pair this
    store had already judged, so the common case is now a *second* judgement
    on a pair that already has reasoning attached — silently blanking it
    would spend the first pass to buy the second. Pass `note=""` to clear one
    on purpose.
    """
    verdicts = load_verdicts()
    previous = verdicts.get(_verdict_key(a_name, b_name), {})
    a, b = sorted(((a_name, a_fm, a_body), (b_name, b_fm, b_body)),
                  key=lambda e: e[0])
    record = {
        "a": a[0], "b": b[0],
        "verdict": verdict,
        "judged": datetime.date.today().isoformat(),
        "a_digest": content_digest(a[1], a[2]),
        "b_digest": content_digest(b[1], b[2]),
        "note": previous.get("note", "") if note is None else note,
    }
    if agreement:
        record["agreement"] = agreement
    verdicts[_verdict_key(a_name, b_name)] = record
    save_verdicts(verdicts)


def candidate_pairs(neighbours=NEIGHBOURS, include_judged=False):
    """Pairs worth judging, with any standing verdict attached.

    A verdict is bound to the content it was passed on. If either entry has
    been rewritten since, the pair returns marked `verdict_stale` and is
    surfaced again — a judgement about text that no longer exists is not a
    judgement.

    Settled pairs drop out of the default view. Three things keep a pair in
    it, and all three are outstanding work rather than open questions:
    a `duplicate` verdict nobody has merged yet, a `contradict` agreement
    nobody has reconciled yet, and a verdict passed without the agreement
    axis being answered at all.

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
        p["agreement"] = v.get("agreement") if v else None
        p["judged"] = v.get("judged", "") if v else ""
        p["note"] = v.get("note", "") if v else ""
        p["verdict_stale"] = bool(v) and not (
            v.get("a_digest") == digests.get(v.get("a"))
            and v.get("b_digest") == digests.get(v.get("b")))
        settled = (v and not p["verdict_stale"]
                   and p["verdict"] in ("distinct", "overlap")
                   and p["agreement"] == "agree")
        if settled and not include_judged:
            continue
        out.append(p)
    return out, skipped


def standing_contradictions():
    """Pairs judged to disagree, where that judgement still applies.

    A verdict is bound to the text it was passed on, so rewriting either
    entry drops the pair out of here and back into `candidates` — resolving a
    contradiction by editing is therefore self-clearing, and claiming one
    about text that no longer exists is impossible. Archived entries are out
    too: retiring an entry is already the decision that it no longer speaks.
    """
    docs, _ = _candidate_docs()
    digests = {d["name"]: content_digest(d["fm"], d["body"]) for d in docs}
    live = {d["name"] for d in docs}
    out = []
    for v in load_verdicts().values():
        if v.get("agreement") != "contradict":
            continue
        a, b = v.get("a"), v.get("b")
        if a not in live or b not in live:
            continue
        if not (v.get("a_digest") == digests[a] and v.get("b_digest") == digests[b]):
            continue
        out.append({"a": a, "b": b, "verdict": v.get("verdict", ""),
                    "judged": v.get("judged", ""), "note": v.get("note", "")})
    out.sort(key=lambda p: (p["a"], p["b"]))
    return out


# --- Consolidation: what a judged pair leaves undone ------------------------
# `judge` records what two entries are to each other. It does not record
# whether anything was *done* about it, and that turned out to be the gap.
#
# The roadmap scoped this command as "propose merges", queued off the pairs
# standing at `duplicate`. Measured against this store's own ledger, that
# queue is empty and structurally likely to stay empty: 87 verdicts over two
# full passes, **zero** duplicates. A store curated by an agent that judges
# pairs as it writes them does not accumulate duplicates — it accumulates
# `overlap`, 44 of the 87 here.
#
# The defect lives in that overlap bucket. `judge` prints "'kb.py link a b'
# if they are not linked yet" once, when the verdict is passed, and then the
# pair settles and drops out of `candidates` forever — so the advice is given
# exactly once and never checked. Seven of this store's 44 overlapping pairs
# had no edge between them. Nothing else can see that: `lint` catches links
# that point nowhere and entries that nobody links to, and both of those are
# properties of a single entry. A missing edge between two well-connected
# entries is a property of a *pair*, and only the ledger knows the pair is
# real.
#
# So `consolidate` reads the ledger and reports what each standing verdict
# still owes: a `duplicate` nobody merged, an `overlap` nobody linked. It
# proposes and never rewrites, for the same reason `candidates` refuses to
# rule — merging is a judgement, and so is deciding an edge is not worth
# drawing.
MIN_PASSAGE_TOKENS = 25
# How far the best-matching entry must beat the runner-up before a passage is
# worth reading. Measured below: 1.5 holds recall at 7 of 7 while dropping the
# queue from 72 passages to 28. At 2.0 recall collapses to 1 of 7.
RESTATEMENT_MARGIN = 1.5
CONSOLIDATE_CAVEAT = (
    "Proposals, not decisions — each one is a judgement someone makes by "
    "reading the entries."
)


def _passages(body):
    """A body split into the units a person would move: paragraphs and items.

    List items and table rows are their own passages rather than being glued
    into the surrounding paragraph, because that is the granularity at which
    procedures actually get restated — `persist-insight-to-knowledge-base`
    repeats `distill-session-into-memory` a numbered step at a time.
    """
    out, cur = [], []
    for line in body.splitlines():
        if re.match(r"^\s*(\d+\.|[-*+]|\|)\s", line) or not line.strip():
            if cur:
                out.append("\n".join(cur))
            cur = [line] if line.strip() else []
        else:
            cur.append(line)
    if cur:
        out.append("\n".join(cur))
    return [p for p in out if len(tokenize(p)) >= MIN_PASSAGE_TOKENS]


def _bm25_scorer(docs):
    """BM25 over a fixed corpus, as a function of (query tokens, doc tokens).

    Deliberately raw BM25 and not `rank()`. `rank` layers type, confidence and
    recency weights on top, which are right when a *person* asks a question
    and wrong here: whether a paragraph restates an entry has nothing to do
    with how recently that entry was verified.
    """
    n = len(docs) or 1
    df = collections.Counter()
    for d in docs:
        df.update(set(d["doc_tokens"]))
    avgdl = sum(len(d["doc_tokens"]) for d in docs) / n

    def score(q_tokens, d_tokens):
        tf = collections.Counter(d_tokens)
        dl = len(d_tokens) or 1
        total = 0.0
        for term in set(q_tokens):
            f = tf.get(term, 0)
            if not f:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            total += idf * (f * (BM25_K1 + 1)) / (
                f + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl)
            )
        return total

    return score


def restatements(margin=RESTATEMENT_MARGIN, docs=None):
    """Passages that read as if they belong in a different entry.

    The sub-entry half of consolidation, and the metric `dupes` uses does not
    find it. Seven hand-written restatements were planted in a copy of this
    store — each a paragraph in one entry restating another entry's claim in
    different words, the shape an agent produces when it re-records something
    already held. Over 2728 (passage, entry) pairs:

        passage shingle-containment, best entry     20 pairs, 1 of 7
        passage as a BM25 query, best entry        124 pairs, 7 of 7

    Containment fails for the same reason it failed at whole-entry scale in
    [[kb-duplicate-detection-limits]]: shingles measure shared *phrasing*, and
    a restatement is precisely what shares none. Asking instead "of everything
    here, which entry is this paragraph most like" is the framing that rescued
    duplicate detection, applied one level down.

    Two filters then cut the queue without costing recall:

    - **It must beat its own host**, scored with the passage itself removed —
      a paragraph that is more at home in another entry than in the one it is
      written in. Removal is what makes the test mean anything; leave the
      passage in and its host wins every time, trivially.
    - **A margin over the runner-up**, because a paragraph that genuinely
      restates one entry points at it decisively.

    Together: 28 passages of 2728 pairs (1%), still 7 of 7.

    Like `candidates`, this blocks and refuses to rule — most of what it puts
    up is an entry legitimately discussing its neighbour. Returns proposals,
    best first.
    """
    if docs is None:
        docs, _ = _candidate_docs()
    for d in docs:
        d["doc_tokens"] = tokenize(
            f"{d['name']} {d['fm'].get('description', '')} {d['body']}")
    score = _bm25_scorer(docs)
    by_name = {d["name"]: d for d in docs}
    verdicts = load_verdicts()

    out = []
    for host in docs:
        for passage in _passages(host["body"]):
            q = tokenize(passage)
            others = sorted(
                ((score(q, d["doc_tokens"]), d["name"]) for d in docs
                 if d["name"] != host["name"]),
                key=lambda t: (-t[0], t[1]))
            if not others:
                continue
            (best, target), runner_up = others[0], (others[1][0] if len(others) > 1 else 0.0)
            if best <= 0:
                continue
            host_without = score(q, tokenize(
                f"{host['name']} {host['fm'].get('description', '')} "
                f"{host['body'].replace(passage, ' ')}"))
            if best <= host_without or best < margin * max(runner_up, 1e-9):
                continue
            v = verdicts.get(_verdict_key(host["name"], target))
            out.append({
                "host": host["name"], "target": target,
                "score": round(best, 1), "host_score": round(host_without, 1),
                "runner_up": round(runner_up, 1),
                "passage": passage.strip(),
                "linked": (target in (host["fm"].get("links") or [])
                           or host["name"] in (by_name[target]["fm"].get("links") or [])),
                "mentions_target": f"[[{target}]]" in passage,
                "verdict": (v or {}).get("verdict", ""),
            })
    out.sort(key=lambda p: (-p["score"], p["host"], p["target"]))
    return out


def nearest_entries(passage, docs=None, limit=5):
    """Which existing entries a not-yet-written claim reads most like.

    The restatement test from `restatements()` with the host term dropped,
    because a claim being captured has no host yet: score the passage as a
    BM25 query over every entry and rank. Two things were measured on this
    store before this was wired into `capture` (see
    [[kb-capture-is-a-check-not-an-extractor]]):

    - Fed a **true** restatement (each entry's own description handed back in),
      the top-ranked entry is the source entry 30 of 30 times, and the existing
      `RESTATEMENT_MARGIN` of 1.5 over the runner-up fires on 29 of 30 — never
      on the wrong entry.
    - Fed a **genuinely new** claim (each entry held out of the corpus first),
      the same margin fires on 7 of 30, and all 7 name an entry the author had
      in fact linked to. So a fire is never noise: it is either the entry this
      claim restates or the entry it belongs next to.

    Returns `[{"name", "score", "ratio", "decisive"}]`, best first, where
    `ratio` is over the runner-up and `decisive` is `ratio >= margin`.
    """
    if docs is None:
        docs, _ = _candidate_docs()
    if not docs:
        return []
    for d in docs:
        d["doc_tokens"] = tokenize(
            f"{d['name']} {d['fm'].get('description', '')} {d['body']}")
    score = _bm25_scorer(docs)
    q = tokenize(passage)
    ranked_docs = sorted(((score(q, d["doc_tokens"]), d["name"]) for d in docs),
                         key=lambda t: (-t[0], t[1]))
    runner_up = ranked_docs[1][0] if len(ranked_docs) > 1 else 0.0
    out = []
    for i, (s, name) in enumerate(ranked_docs[:limit or None]):
        if s <= 0:
            break
        ratio = (s / max(runner_up, 1e-9)) if i == 0 else 0.0
        out.append({"name": name, "score": round(s, 1),
                    "ratio": round(ratio, 2) if i == 0 else None,
                    "decisive": bool(i == 0 and ratio >= RESTATEMENT_MARGIN)})
    return out


def consolidation_report(margin=RESTATEMENT_MARGIN):
    """Everything the standing verdicts still owe, in three queues.

    A verdict is bound to the text it was passed on, so a pair whose entries
    have been rewritten since is deliberately absent from all three: it is
    already back in `candidates` to be judged again, and acting on a
    judgement about text that no longer exists is worse than acting on none.
    Archived entries are absent for the same reason they leave retrieval —
    retiring an entry is already the decision that it no longer speaks.
    """
    docs, skipped = _candidate_docs()
    digests = {d["name"]: content_digest(d["fm"], d["body"]) for d in docs}
    by_name = {d["name"]: d for d in docs}

    merges, edges = [], []
    for v in load_verdicts().values():
        a, b = v.get("a"), v.get("b")
        if a not in by_name or b not in by_name:
            continue
        if not (v.get("a_digest") == digests[a] and v.get("b_digest") == digests[b]):
            continue
        item = {"a": a, "b": b, "judged": v.get("judged", ""),
                "note": v.get("note", ""),
                "a_description": by_name[a]["fm"].get("description", ""),
                "b_description": by_name[b]["fm"].get("description", "")}
        if v.get("verdict") == "duplicate":
            merges.append(item)
        elif v.get("verdict") == "overlap":
            linked = (b in (by_name[a]["fm"].get("links") or [])
                      or a in (by_name[b]["fm"].get("links") or []))
            if not linked:
                edges.append(item)
    merges.sort(key=lambda p: (p["a"], p["b"]))
    edges.sort(key=lambda p: (p["a"], p["b"]))
    return {"merges": merges, "missing_edges": edges,
            "restatements": restatements(margin=margin, docs=docs),
            "too_short": skipped}


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
            "authority": fm.get("authority", ""),
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
        # A binding rule and an overridable preference can read with the same
        # imperative grammar ("Jerry asked that...", "must"); this is the one
        # structural signal that a context pack — what an agent actually acts
        # on — carries the difference forward. See kb-instruction-content-lint.
        authority_tag = ""
        if hit.get("authority") == "rule":
            authority_tag = "  [RULE — binding, do not treat as optional]"
        elif hit.get("authority") == "preference":
            authority_tag = "  [preference — overridable]"
        header = (
            f"### {hit['name']}  ({hit['type']}){authority_tag}\n"
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


# --- Measuring retrieval ----------------------------------------------------
# A fixed set of task-shaped questions with the entry each one must return, so
# a change to the ranker (or to the store) shows up as a number rather than as
# a feeling. What the set can and cannot see is measured in ROADMAP Phase 7:
# it detects gross breakage and is blind to parameter tuning, which is why
# nothing here asserts a tuned constant.
GOLDEN_FILE = KB_DIR / "golden.json"


def load_golden(path=None):
    """The golden query set. A missing file means nobody has written one."""
    path = GOLDEN_FILE if path is None else path
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: could not load {path}: {e}", file=sys.stderr)
        sys.exit(2)
    queries = []
    for q in data.get("queries", []):
        if not isinstance(q, dict) or not q.get("query") or not q.get("expect"):
            continue
        queries.append({
            "query": str(q["query"]),
            "expect": str(q["expect"]),
            "also_ok": [str(x) for x in (q.get("also_ok") or [])],
        })
    return queries


def eval_report(golden=None, docs=None, rank_fn=None):
    """Score retrieval against the golden query set.

    Three numbers, because they answer different questions. `success@1` is
    what a caller reading one hit gets. `MRR` is how far down the right entry
    sits when it is not first. `recall@3`/`recall@5` are what `kb.py context`
    actually delivers, since a context pack is a handful of entries and not a
    single answer — that is the metric to watch when the store grows.

    `also_ok` names are a defensible answer to the same question. They count
    for recall (the pack is useful) but never for `success@1` (the question
    had one best answer). `rank_fn` is injectable so a caller can score a
    deliberately degraded ranker and find out whether the set can still tell
    the difference — see `tests/test_retrieval_golden.py`.
    """
    golden = load_golden() if golden is None else golden
    docs = entry_documents() if docs is None else docs
    rank_fn = (lambda q: rank(q, docs=docs)) if rank_fn is None else rank_fn
    # An expectation is only answerable if its entry is in the retrieval set.
    # Archiving takes an entry out of that set without deleting the file, so
    # testing existence alone lets an archived expectation score as a miss on
    # every run forever — the same silent fixture rot a deleted entry causes,
    # by the commoner route.
    known = {fm.get("name", path.stem) for _, path, fm, _, _ in docs
             if not is_archived(fm)}

    rows = []
    for g in golden:
        names = [h["name"] for h in rank_fn(g["query"])]
        acceptable = {g["expect"], *g["also_ok"]}
        position = names.index(g["expect"]) + 1 if g["expect"] in names else None
        rows.append({
            "query": g["query"],
            "expect": g["expect"],
            "also_ok": g["also_ok"],
            "rank": position,
            "reciprocal_rank": round(1 / position, 4) if position else 0.0,
            "acceptable_rank": next(
                (i + 1 for i, n in enumerate(names) if n in acceptable), None),
            "top": names[:5],
            # An expectation naming an entry that no longer exists is a broken
            # fixture, not a retrieval failure. Kept separate for that reason.
            "unresolved": sorted(n for n in acceptable if n not in known),
        })

    n = len(rows)
    def share(pred):
        return round(sum(1 for r in rows if pred(r)) / n, 4) if n else 0.0

    return {
        "summary": {
            "queries": n,
            "entries": len(docs),
            "success_at_1": share(lambda r: r["rank"] == 1),
            "mrr": round(sum(r["reciprocal_rank"] for r in rows) / n, 4) if n else 0.0,
            "recall_at_3": share(lambda r: r["acceptable_rank"] is not None
                                 and r["acceptable_rank"] <= 3),
            "recall_at_5": share(lambda r: r["acceptable_rank"] is not None
                                 and r["acceptable_rank"] <= 5),
            "unresolved": sorted({name for r in rows for name in r["unresolved"]}),
        },
        "queries": rows,
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


def _parse_within(value):
    """'14d' or '14' -> 14. argparse turns a raised ValueError into a clean error."""
    s = value.strip().lower()
    if s.endswith("d"):
        s = s[:-1]
    days = int(s)
    if days < 0:
        raise ValueError("must not be negative")
    return days


# Frontmatter fields whose change is bookkeeping rather than a change of claim.
# `confidence` sits here with the others because `verify` moves it as routine
# maintenance; a demotion that matters shows up as a body edit alongside it.
HISTORY_MECHANICAL_FIELDS = ("last_verified", "confidence", "links", "archived", "due")

HISTORY_CHANGES = {
    "created": "written",
    "claim": "claim changed",
    "body": "edited",
    "metadata": "verified/linked",
}


def _git(*args):
    """Run a git command in the repo, or return None if git cannot answer.

    Every caller treats None as "this store has no history to show" rather than
    as an error: a KB scaffolded into a directory that is not a git repo, or a
    machine without git, is a supported way to run and must not crash.
    """
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(ROOT),
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _description_at(blob):
    m = re.search(r"^description:[ \t]*(.*)$", blob, re.MULTILINE)
    return m.group(1).strip() if m else None


def entry_history(path, limit=0):
    """Every revision of one entry, oldest first, with what each one changed.

    Returns None when there is no history to read (no git, not a repository).
    Returns [] when the file is real but has never been committed.

    The classification is the point. `kb.py verify` touches an entry far more
    often than an author does, so an undifferentiated `git log` buries the two
    revisions that rewrote a claim under twenty that only stamped a date.
    """
    rel = str(path.relative_to(ROOT))
    if _git("rev-parse", "--git-dir") is None:
        return None
    # A repository with no commits at all makes `git log` exit non-zero, which
    # is not the same failure as having no repository: it means this entry has
    # no history yet, exactly like an entry that is simply untracked.
    log = _git("log", "--format=%H%x00%ad%x00%s", "--date=short", "--follow", "--", rel)
    if log is None:
        return []

    revisions = []
    for line in log.strip().splitlines():
        if not line:
            continue
        parts = line.split("\0")
        if len(parts) != 3:
            continue
        revisions.append(parts)
    revisions.reverse()  # oldest first: a history reads forwards

    out = []
    previous_claim = None
    for index, (sha, date, subject) in enumerate(revisions):
        blob = _git("show", f"{sha}:{rel}")
        claim = _description_at(blob) if blob is not None else None
        if index == 0:
            change = "created"
        elif claim != previous_claim:
            change = "claim"
        elif _revision_touched_prose(revisions[index - 1][0], sha, rel):
            change = "body"
        else:
            change = "metadata"
        out.append({
            "commit": sha[:7],
            "date": date,
            "subject": subject,
            "change": change,
            "claim": claim,
        })
        previous_claim = claim

    if limit and len(out) > limit:
        out = out[-limit:]
    return out


def _revision_touched_prose(before_sha, after_sha, rel):
    """True if the revision changed anything but bookkeeping frontmatter."""
    diff = _git("diff", "--unified=0", before_sha, after_sha, "--", rel)
    if diff is None:
        return True
    for line in diff.splitlines():
        if not line[:1] in ("+", "-") or line[:3] in ("+++", "---"):
            continue
        content = line[1:]
        if any(content.startswith(f"{field}:") for field in HISTORY_MECHANICAL_FIELDS):
            continue
        if content.strip():
            return True
    return False


def history_is_shallow():
    """A shallow clone has a truncated history and must say so before it lies.

    Actions/checkout defaults to depth 1, so a history read in CI would show
    one revision and look like an entry that has never changed.
    """
    out = _git("rev-parse", "--is-shallow-repository")
    return out is not None and out.strip() == "true"


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

    # A contradiction is a property of a pair, so it lands on both entries:
    # neither is identifiable as the wrong one without reading them.
    disagrees = collections.defaultdict(list)
    for pair in standing_contradictions():
        disagrees[pair["a"]].append(pair["b"])
        disagrees[pair["b"]].append(pair["a"])

    report = []
    for t, path, fm in entries:
        # Archiving is the decision that an entry no longer needs attention.
        # Continuing to flag it as stale would make the queue un-clearable.
        if is_archived(fm):
            continue
        name = fm.get("name", path.stem)
        confidence = fm.get("confidence", "")
        reasons = []

        for other in sorted(disagrees.get(name, [])):
            reasons.append(("contradiction",
                            f"judged to disagree with {other}"))

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


def due_report(within_days=None):
    """Prospective entries whose due date has arrived or is approaching.

    `triage` already flags overdue entries as a problem; this answers a
    different question — "what is coming up" — so the scheduled workflow (and
    an agent starting a session) can see a due date before it lapses, not just
    after. Unparseable due dates are `triage`'s job (reported as
    `invalid-due`), not this one's, so they are silently skipped here.
    """
    today = datetime.date.today()
    cutoff = today + datetime.timedelta(days=within_days) if within_days is not None else None
    rows = []
    for t, path in iter_entries():
        if t != "prospective":
            continue
        try:
            fm, _ = parse_frontmatter(path)
        except OSError:
            continue
        if is_archived(fm):
            continue
        due = fm.get("due")
        if not due:
            continue
        try:
            due_date = datetime.date.fromisoformat(due)
        except ValueError:
            continue
        if cutoff is not None and due_date > cutoff:
            continue
        rows.append({
            "name": fm.get("name", path.stem),
            "due": due,
            "days": (due_date - today).days,
            "overdue": due_date < today,
            "description": fm.get("description", ""),
            "path": str(path.relative_to(ROOT)),
        })

    rows.sort(key=lambda r: r["due"])
    return rows


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


def stats_report():
    """What the store is made of, as counts rather than as a list to read.

    `triage` and `status` answer "what needs doing" one entry at a time. This
    answers the questions that are only visible in aggregate — is the store
    growing or drifting, is the graph connected, is the confidence mix honest,
    is retrieval scoring the way it did last month.
    """
    today = datetime.date.today()

    entries = []
    inbound = collections.Counter()
    for t, path in iter_entries():
        try:
            fm, body = parse_frontmatter(path)
        except OSError:
            continue
        entries.append((t, path, fm, body))
        for link in fm.get("links") or []:
            inbound[link] += 1

    by_type = collections.Counter()
    by_confidence = collections.Counter()
    by_effective = collections.Counter()
    by_month = collections.Counter()
    ages, words, edges = [], [], 0
    archived = orphans = unlinked = never_verified = decayed = 0

    for t, path, fm, body in entries:
        name = fm.get("name", path.stem)
        by_type[t] += 1
        by_confidence[fm.get("confidence", "")] += 1
        effective, decayed_by = effective_confidence(fm, today)
        by_effective[effective] += 1
        if decayed_by:
            decayed += 1
        if is_archived(fm):
            archived += 1

        links = fm.get("links") or []
        edges += len(links)
        if not links:
            unlinked += 1
        if not inbound[name]:
            orphans += 1

        lv = fm.get("last_verified")
        if lv:
            try:
                ages.append((today - datetime.date.fromisoformat(str(lv))).days)
            except ValueError:
                pass
        else:
            never_verified += 1

        created = fm.get("created")
        if created:
            by_month[str(created)[:7]] += 1
        words.append(len(body.split()))

    total = len(entries)

    def median(values):
        if not values:
            return None
        s = sorted(values)
        mid = len(s) // 2
        if len(s) % 2:
            return s[mid]
        middle = (s[mid - 1] + s[mid]) / 2
        return int(middle) if middle.is_integer() else middle

    return {
        "entries": total,
        "archived": archived,
        "by_type": {t: by_type[t] for t in TYPES if by_type[t]},
        "by_confidence": {c: by_confidence[c] for c in CONFIDENCE_LEVELS
                          if by_confidence[c]},
        "by_effective_confidence": {c: by_effective[c] for c in CONFIDENCE_LEVELS
                                    if by_effective[c]},
        "decayed": decayed,
        "links": {
            "edges": edges,
            # Average outbound degree: how many other entries a typical entry
            # points at. The graph is undirected in practice (links are
            # reciprocated by convention), so this is the honest density
            # number rather than edges/possible-pairs, which is ~0 at any size.
            "per_entry": round(edges / total, 2) if total else 0.0,
            "orphans": orphans,
            "unlinked": unlinked,
        },
        "age_days": {
            "median": median(ages),
            "oldest": max(ages) if ages else None,
            "never_verified": never_verified,
        },
        "body_words": {"median": median(words), "total": sum(words)},
        "created_by_month": [[m, by_month[m]] for m in sorted(by_month)],
        "review_forecast": review_forecast(today),
    }


def review_forecast(today=None):
    """When the store's re-verification work lands, if nothing else changes.

    Every live entry's review date is `last_verified + STALE_DAYS`, so the
    shape of the coming workload is fixed the moment the entry is written.
    Nothing else reports it: `triage` and `status` both describe today, and a
    store whose entries were all written in the same week therefore reads
    perfectly clean right up to the day the whole of it goes stale at once.

    The window matters more than the dates. A store spread evenly across the
    cycle retires a slice of itself each week; a store concentrated into a few
    days has no slice small enough to do, so the queue arrives whole and the
    natural repair — re-verify everything in one sweep — sets the spread to
    zero and schedules the same pile-up exactly one cycle later.
    """
    today = today or datetime.date.today()
    by_date = collections.Counter()
    undated = 0
    for t, path in iter_entries():
        try:
            fm, _ = parse_frontmatter(path)
        except OSError:
            continue
        if is_archived(fm):
            continue
        try:
            due = (datetime.date.fromisoformat(str(fm.get("last_verified")))
                   + datetime.timedelta(days=STALE_DAYS))
        except (TypeError, ValueError):
            # No date, or one `triage` already reports as broken. Either way
            # this entry has no review date to forecast; it is counted so the
            # forecast cannot silently describe a subset of the store.
            undated += 1
            continue
        by_date[due.isoformat()] += 1

    dated = sum(by_date.values())
    forecast = {
        "today": today.isoformat(),
        "cycle_days": STALE_DAYS,
        "dated": dated,
        "undated": undated,
        "first": None,
        "last": None,
        "span_days": None,
        "busiest": None,
        "already_due": 0,
        "is_cohort": False,
        "by_date": [],
    }
    if not dated:
        return forecast

    dates = sorted(by_date)
    span = (datetime.date.fromisoformat(dates[-1])
            - datetime.date.fromisoformat(dates[0])).days
    forecast.update({
        "first": dates[0],
        "last": dates[-1],
        "span_days": span,
        # Ties go to the earliest date: the first day the load appears is the
        # one worth naming, not the last day it is still that size.
        "busiest": min(dates, key=lambda d: (-by_date[d], d)),
        "already_due": sum(n for d, n in by_date.items()
                           if datetime.date.fromisoformat(d) <= today),
        "is_cohort": dated >= COHORT_MIN_ENTRIES and span <= STALE_DAYS * COHORT_RATIO,
        "by_date": [[d, by_date[d]] for d in dates],
    })
    return forecast


def format_review_forecast(f):
    """The forecast as the one or two lines a board can end with."""
    if not f["dated"]:
        return []
    span, cycle = f["span_days"], f["cycle_days"]
    peak = dict(f["by_date"])[f["busiest"]]
    lines = [
        f"Review load: {f['dated']} entr{'y' if f['dated'] == 1 else 'ies'} "
        f"come due {f['first']} → {f['last']} — {span}d wide inside a "
        f"{cycle}d review cycle, busiest {f['busiest']} ({peak})."
    ]
    if f["already_due"]:
        lines.append(f"  {f['already_due']} of them already past review.")
    if f["undated"]:
        lines.append(f"  {f['undated']} entr{'y' if f['undated'] == 1 else 'ies'} "
                     "have no usable last_verified and are not in this forecast.")
    if f["is_cohort"]:
        lines.append("  That is one cohort, not a spread: re-verifying them "
                     "together re-dates them together, so the same pile-up "
                     f"returns {cycle}d later. Spread the sweep to spread it.")
    return lines


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
    # The board above is a snapshot; a clean one says nothing about whether
    # the store is about to need all of its attention on the same day.
    if not (args.type or args.status):
        for line in format_review_forecast(review_forecast()):
            print(line)
    print("Run 'kb.py status --legend' for what each status means.")


def cmd_stats(args):
    s = stats_report()
    if args.json:
        print(json.dumps(s, indent=2))
        return
    if not s["entries"]:
        print("empty store")
        return

    def row(label, value):
        print(f"  {label:<22} {value}")

    live = s["entries"] - s["archived"]
    print(f"{s['entries']} entries ({live} in retrieval, {s['archived']} archived)")

    print("\nBY TYPE")
    for t, n in s["by_type"].items():
        row(t, n)

    print("\nCONFIDENCE (as written → as read today)")
    for c in CONFIDENCE_LEVELS:
        written = s["by_confidence"].get(c, 0)
        read = s["by_effective_confidence"].get(c, 0)
        if written or read:
            row(c, f"{written} → {read}")
    if s["decayed"]:
        row("decayed by age", s["decayed"])

    print("\nGRAPH")
    row("links", s["links"]["edges"])
    row("per entry", s["links"]["per_entry"])
    row("nothing links to it", s["links"]["orphans"])
    row("links to nothing", s["links"]["unlinked"])

    print("\nAGE AND SIZE")
    age = s["age_days"]
    row("median days verified", age["median"] if age["median"] is not None else "—")
    row("oldest", f"{age['oldest']}d" if age["oldest"] is not None else "—")
    if age["never_verified"]:
        row("never verified", age["never_verified"])
    row("median body words", s["body_words"]["median"])
    row("total body words", s["body_words"]["total"])

    f = s["review_forecast"]
    if f["dated"]:
        print("\nREVIEW LOAD")
        row("comes due", f"{f['first']} → {f['last']}")
        row("window", f"{f['span_days']}d of a {f['cycle_days']}d cycle")
        row("busiest day", f"{f['busiest']} ({dict(f['by_date'])[f['busiest']]})")
        if f["already_due"]:
            row("already past review", f["already_due"])
        if f["undated"]:
            row("no review date", f["undated"])
        if f["is_cohort"]:
            row("shape", "one cohort — the whole store comes due together")

    if s["created_by_month"]:
        print("\nCREATED")
        widest = max(n for _, n in s["created_by_month"])
        for month, n in s["created_by_month"]:
            bar = "#" * max(1, round(n * 24 / widest))
            print(f"  {month}  {bar} {n}")


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


def cmd_due(args):
    rows = due_report(within_days=args.within)
    if args.json:
        print(json.dumps(rows, indent=2))
        return
    if not rows:
        scope = f" within {args.within}d" if args.within is not None else ""
        print(f"nothing due{scope}")
        return
    for r in rows:
        flag = "OVERDUE " if r["overdue"] else f"in {r['days']}d".ljust(8)
        print(f"[{flag}] {r['due']}  {r['name']:30} {r['description']}")
    print(f"\n{len(rows)} entr(ies) due")


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
    if args.field == "links":
        print("refusing to set 'links' as a plain value — it must stay a list; "
              "use 'kb.py link' to add or remove one", file=sys.stderr)
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
        if p["agreement"] == "contradict":
            tags.append("CONTRADICTION standing — reconcile them")
        elif p["verdict"] and not p["agreement"] and not p["verdict_stale"]:
            tags.append("never checked for contradiction")
        suffix = f"  ({'; '.join(tags)})" if tags else ""
        print(f"\n{p['similarity']:.2f}  {p['a']} <-> {p['b']}{suffix}")
        print(f"      {p['a_type']}/{p['b_type']}, {p['shared_tokens']} shared words")
        print(f"      a: {p['a_description']}")
        print(f"      b: {p['b_description']}")
        if p["note"]:
            print(f"      note: {p['note']}")
    if pairs:
        print(f"\n{len(pairs)} pair(s) to judge. {CANDIDATES_CAVEAT}\n"
              f"  kb.py judge <a> <b> {'|'.join(VERDICTS)} "
              f"--agreement {'|'.join(AGREEMENTS)} [--note ...]\n"
              "Two questions per pair, not one: how much they overlap, and "
              "whether they disagree.")
    if skipped:
        print(f"\n{len(skipped)} entr(ies) too short to compare "
              f"(<{MIN_CANDIDATE_TOKENS} distinct words): {', '.join(sorted(skipped))}")


def cmd_consolidate(args):
    report = consolidation_report(margin=args.margin)
    if args.json:
        print(json.dumps(report, indent=2))
        return

    merges, edges = report["merges"], report["missing_edges"]
    restated = report["restatements"]
    if args.only:
        for key in ("merges", "missing_edges", "restatements"):
            if key != args.only:
                report[key] = []
        merges, edges, restated = (report["merges"], report["missing_edges"],
                                   report["restatements"])

    if merges or args.only in (None, "merges"):
        print(f"MERGE — pairs standing at 'duplicate' ({len(merges)})")
        if not merges:
            print("  none. Every pair this store has judged came back "
                  "'overlap' or 'distinct'.")
        for p in merges:
            print(f"\n  {p['a']} <-> {p['b']}   (judged {p['judged']})")
            print(f"      a: {p['a_description']}")
            print(f"      b: {p['b_description']}")
            if p["note"]:
                print(f"      note: {p['note']}")
            print(f"      merge by hand, then: kb.py archive {p['b']}")

    if edges or args.only in (None, "missing_edges"):
        print(f"\nLINK — judged 'overlap', no edge between them ({len(edges)})")
        if not edges:
            print("  none. Every overlapping pair is linked.")
        for p in edges:
            print(f"\n  {p['a']} <-> {p['b']}   (judged {p['judged']})")
            print(f"      a: {p['a_description']}")
            print(f"      b: {p['b_description']}")
            if p["note"]:
                print(f"      note: {p['note']}")
            print(f"      kb.py link {p['a']} {p['b']}")

    if restated or args.only in (None, "restatements"):
        print(f"\nRESTATED — passages that read as another entry's "
              f"({len(restated)})")
        if not restated:
            print("  none.")
        for p in restated:
            tags = []
            if p["linked"]:
                tags.append("already linked")
            if p["mentions_target"]:
                tags.append("passage already cites it")
            if p["verdict"]:
                tags.append(f"judged {p['verdict']}")
            suffix = f"  ({'; '.join(tags)})" if tags else ""
            print(f"\n  {p['host']} -> {p['target']}{suffix}")
            print(f"      {p['score']} vs {p['host_score']} for its own entry, "
                  f"{p['runner_up']} for the next best")
            for line in textwrap.wrap(p["passage"], 72)[:args.lines]:
                print(f"      | {line}")
            print(f"      if it restates that entry, cut it to [[{p['target']}]]")

    total = len(merges) + len(edges) + len(restated)
    print(f"\n{total} proposal(s). {CONSOLIDATE_CAVEAT}")
    if report["too_short"]:
        print(f"{len(report['too_short'])} entr(ies) too short to compare "
              f"(<{MIN_CANDIDATE_TOKENS} distinct words): "
              f"{', '.join(sorted(report['too_short']))}")


def cmd_judge(args):
    a_type, a_path, a_fm, a_body = _require(args.a)
    b_type, b_path, b_fm, b_body = _require(args.b)
    a_name = a_fm.get("name", a_path.stem)
    b_name = b_fm.get("name", b_path.stem)
    if a_name == b_name:
        print("an entry cannot duplicate itself", file=sys.stderr)
        sys.exit(1)
    record_verdict(a_name, a_fm, a_body, b_name, b_fm, b_body,
                   args.verdict, args.note, args.agreement)
    # No entry in .kb/log.md: that log tracks changes to entries, and a verdict
    # changes none. The ledger is its own record and is git-tracked.
    agreed = f" ({args.agreement})" if args.agreement else ""
    print(f"recorded: {a_name} <-> {b_name} = {args.verdict}{agreed}")

    if args.agreement == "contradict":
        # Whatever the overlap verdict says, disagreement is the live problem.
        print("next: both entries are now 'contradicted' in triage and status. "
              "Reconcile them — correct the wrong one, or narrow both until "
              "they can both be true — then re-judge with --agreement agree")
        return
    follow_up = {
        "duplicate": "merge the two by hand, then 'kb.py archive' the loser — "
                     "this pair stays in 'candidates' until you do",
        "overlap": "related but both earn their place; "
                   f"'kb.py link {a_name} {b_name}' if they are not linked yet",
        "distinct": "this pair will stay out of 'candidates' unless either "
                    "entry's text changes",
    }
    print(f"next: {follow_up[args.verdict]}")
    if not args.agreement:
        print("half-judged: you said how much they overlap, not whether they "
              "disagree. This pair stays in 'candidates' until you pass "
              f"--agreement {'|'.join(AGREEMENTS)}")


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
    for _other_type, other in iter_entries():
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
        if h["authority"] == "rule":
            flags += "  [RULE]"
        elif h["authority"] == "preference":
            flags += "  [preference]"
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


def cmd_eval(args):
    report = eval_report()
    if args.json:
        print(json.dumps(report, indent=2))
        return

    s = report["summary"]
    if not s["queries"]:
        print(f"no golden queries — {GOLDEN_FILE.name} is missing or empty")
        return

    rows = report["queries"] if args.all else [r for r in report["queries"]
                                               if r["rank"] != 1]
    for r in rows:
        place = f"#{r['rank']}" if r["rank"] else "absent"
        print(f"{place:>7}  {r['query']}")
        print(f"         want {r['expect']}, got {', '.join(r['top'][:3]) or '(nothing)'}")
    if rows:
        print()

    print(f"{s['queries']} queries over {s['entries']} entries: "
          f"success@1 {s['success_at_1']:.3f}  MRR {s['mrr']:.3f}  "
          f"recall@3 {s['recall_at_3']:.3f}  recall@5 {s['recall_at_5']:.3f}")
    if not args.all:
        print("Only queries whose top hit is wrong are listed; --all shows every query.")
    if s["unresolved"]:
        print(f"\nerror: {len(s['unresolved'])} expected entr(ies) are gone from "
              f"the retrieval set (deleted, renamed or archived): "
              f"{', '.join(s['unresolved'])}", file=sys.stderr)
        print(f"Fix {GOLDEN_FILE.name} — an expectation that cannot resolve "
              "scores as a miss forever.", file=sys.stderr)
        sys.exit(1)


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


HISTORY_CAVEAT = (
    "An entry is corrected in place, so this is the only record of what the "
    "current claim replaced."
)


_LOG_LINE_RE = re.compile(
    r'^- (?P<date>\d{4}-\d{2}-\d{2}) — (?P<action>\S+) '
    r'`(?P<type>[a-z]+)/(?P<slug>[^/]+)\.md`(?: — (?P<detail>.*))?$'
)


def parse_log():
    """`.kb/log.md` structured, most recent first.

    ROADMAP Phase 10: the log already records every mutation, but as a flat
    append-only file nobody reads bottom-to-top. This is the read side —
    still backed by the same file, still not the record of record (that's
    git); it only reorders and makes it filterable.
    """
    if not LOG_FILE.is_file():
        return []
    records = []
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        m = _LOG_LINE_RE.match(line)
        if not m:
            continue
        records.append({
            "date": m.group("date"),
            "action": m.group("action"),
            "type": m.group("type"),
            "name": m.group("slug"),
            "detail": m.group("detail") or "",
        })
    records.reverse()
    return records


def cmd_log(args):
    records = parse_log()
    if args.type:
        records = [r for r in records if r["type"] == args.type]
    if args.action:
        records = [r for r in records if r["action"] == args.action]
    if args.name:
        records = [r for r in records if r["name"] == args.name]
    shown = records[: args.limit] if args.limit else records

    if args.json:
        print(json.dumps(shown, indent=2))
        return

    if not shown:
        print("no matching log entries")
        return
    for r in shown:
        detail = f"  — {r['detail']}" if r["detail"] else ""
        print(f"{r['date']}  {r['action']:10} {r['type']}/{r['name']}{detail}")
    if len(records) > len(shown):
        print(f"\n{len(records) - len(shown)} more — raise --limit to see them (0 for all).")


def cmd_history(args):
    entry_type, path, fm, _ = _require(args.name)
    name = fm.get("name") or path.stem
    revisions = entry_history(path, limit=args.limit)

    if revisions is None:
        print(f"no history for '{name}' — {ROOT} is not a git repository, "
              "or git is unavailable", file=sys.stderr)
        sys.exit(1)
    if not revisions:
        print(f"'{name}' has never been committed — nothing to show yet")
        return

    if args.json:
        print(json.dumps({
            "name": name,
            "type": entry_type,
            "path": str(path.relative_to(ROOT)),
            "shallow": history_is_shallow(),
            "revisions": revisions,
        }, indent=2))
        return

    print(f"\n{name}  ({entry_type})")
    print(f"{len(revisions)} revision{'s' if len(revisions) != 1 else ''}, oldest first\n")
    if history_is_shallow():
        print("  ! shallow clone — this history is truncated and may be missing "
              "revisions\n")

    for revision in revisions:
        label = HISTORY_CHANGES[revision["change"]]
        print(f"  {revision['date']}  {revision['commit']}  {label:15} "
              f"{revision['subject']}")
        if revision["change"] in ("created", "claim") and revision["claim"]:
            for line in textwrap.wrap(revision["claim"], width=76):
                print(f"      | {line}")
    claim_changes = sum(1 for r in revisions if r["change"] == "claim")
    if claim_changes:
        print(f"\n  the one-line claim has been rewritten {claim_changes} time"
              f"{'s' if claim_changes != 1 else ''} — the quoted blocks above are "
              "every wording it has had, oldest first")
    print(f"\n{HISTORY_CAVEAT}")


class EntryError(Exception):
    """A caller-fixable problem with a requested entry (bad type, bad date,
    colliding slug). Raised rather than exited so the MCP server, which runs
    in-process, can turn it into a tool error instead of dying."""

    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code


def scaffold_entry(entry_type, name, due=None, description=None, body=None,
                   links=(), source=None):
    """Write a new entry from the template. Shared by `new` and `capture`.

    Returns the destination path; raises EntryError on anything the caller
    could fix.
    """
    if entry_type not in TYPES:
        raise EntryError(f"type must be one of: {', '.join(TYPES)}")
    if entry_type == "prospective" and not due:
        raise EntryError("--due is required for --type prospective")
    if due:
        try:
            datetime.date.fromisoformat(due)
        except ValueError:
            raise EntryError(f"--due is not a valid date: {due!r}") from None
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise EntryError(f"name must contain at least one letter or digit: {name!r}")
    folder = MEMORY / entry_type
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{slug}.md"
    if dest.exists():
        raise EntryError(f"entry already exists: {dest.relative_to(ROOT)}")
    today = datetime.date.today().isoformat()
    try:
        text = TEMPLATE.read_text(encoding="utf-8")
    except OSError as e:
        raise EntryError(f"error: could not read template {TEMPLATE}: {e}", code=2) from None
    text = text.replace("REPLACE-ME-kebab-case-slug", slug)
    text = text.replace("type: semantic", f"type: {entry_type}")
    text = text.replace("created: 1970-01-01", f"created: {today}")
    text = text.replace("last_verified: 1970-01-01", f"last_verified: {today}")
    if entry_type == "prospective":
        text = text.replace("due: 1970-01-01", f"due: {due}")
    else:
        text = "".join(
            line for line in text.splitlines(keepends=True)
            if not line.startswith("due:")
        )
    if description:
        text = text.replace("description: one-line summary",
                            f"description: {_fm_scalar(description)}")
    if source:
        text = text.replace("source: where this came from",
                            f"source: {_fm_scalar(source)}")
    if links:
        text = text.replace("links: []", f"links: [{', '.join(links)}]")
    if body is not None:
        m = re.match(r"(---\n.*?\n---\n)(.*)", text, re.S)
        if not m:
            raise EntryError(f"error: template {TEMPLATE} has no frontmatter block", code=2)
        text = f"{m.group(1)}\n{body.strip()}\n"
    dest.write_text(text, encoding="utf-8")
    _append_log(entry_type, slug, today)
    return dest


def _fm_scalar(value):
    """A one-line frontmatter value, made safe for the parser above.

    `parse_frontmatter` is line-based and splits on the *first* colon, so a
    colon inside the value is harmless; it also never unquotes, so adding
    quotes would store the quotes. That leaves exactly one value shape that
    misparses — one that looks like a list — and one that breaks the block:
    a newline. Both are handled here and nothing else is touched.
    """
    value = " ".join(str(value).split())
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1].strip()
    return value


def _scaffold_or_exit(**kwargs):
    try:
        return scaffold_entry(**kwargs)
    except EntryError as e:
        print(str(e), file=sys.stderr)
        sys.exit(e.code)


def cmd_new(args):
    dest = _scaffold_or_exit(entry_type=args.type, name=args.name, due=args.due)
    print(f"created {dest.relative_to(ROOT)}")


def _first_sentence(text, limit=200):
    """The claim line an author would write, taken from what they already wrote."""
    flat = " ".join(text.split()).lstrip("-*>#[ ").strip()
    m = re.match(r"(.+?[.!?])(\s|$)", flat)
    sentence = (m.group(1) if m else flat).rstrip(".")
    if len(sentence) > limit:
        sentence = sentence[:limit].rsplit(" ", 1)[0] + "…"
    return sentence


def _source_label(source):
    """What to record as an entry's `source`.

    A path only means something to a later reader if it is inside the repo; a
    scratch file in a temp directory is gone by the time anyone reads the
    entry, so it is recorded as what it is instead of as a dead path.
    """
    if source in (None, "-"):
        return "captured passage"
    try:
        return str(pathlib.Path(source).resolve().relative_to(ROOT))
    except ValueError:
        return "captured passage"


def read_passage(source=None, text=None):
    """The claim to capture: from --text, from a file, or from stdin via `-`."""
    if text is not None:
        passage = text
    elif source in (None, "-"):
        passage = sys.stdin.read()
    else:
        path = pathlib.Path(source)
        try:
            passage = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"error: could not read {source}: {e}", file=sys.stderr)
            sys.exit(2)
    passage = passage.strip()
    if not passage:
        print("error: nothing to capture — the passage is empty", file=sys.stderr)
        sys.exit(1)
    return passage


def capture_report(passage, limit=5):
    """What the store already holds that this claim reads like."""
    return {"passage": passage, "neighbours": nearest_entries(passage, limit=limit)}


def cmd_capture(args):
    passage = read_passage(getattr(args, "source", None), getattr(args, "text", None))

    if args.extend:
        if args.type or args.name:
            print("error: pass either --extend, or --type with --name — not both",
                  file=sys.stderr)
            sys.exit(1)
        # No neighbour scan here: you have already decided where this goes.
        entry_type, path, fm, body = _require(args.extend)
        write_body(path, f"{body.rstrip()}\n\n{passage}")
        _append_log(entry_type, path.stem, datetime.date.today().isoformat(),
                    action="extended", detail="captured passage appended")
        if args.json:
            print(json.dumps({"extended": fm.get("name", path.stem),
                              "path": str(path.relative_to(ROOT))}, indent=2))
            return
        print(f"extended {path.relative_to(ROOT)}")
        print(f"the appended passage is not verification — re-read it: "
              f"kb.py show {path.stem}")
        return

    report = capture_report(passage)
    neighbours = report["neighbours"]
    top = neighbours[0] if neighbours else None

    if args.json:
        # A check-only view: writing an entry has output (a path, a link, a
        # next step) that belongs on stdout as prose, not wrapped in JSON.
        print(json.dumps(report, indent=2))
        return

    if not neighbours:
        print("no existing entry reads like this — the store is empty or the "
              "passage shares no terms with it")
    else:
        print("nearest entries — read before you write:")
        for n in neighbours:
            mark = "  <- decisive" if n["decisive"] else ""
            ratio = f" ({n['ratio']}x runner-up)" if n["ratio"] else ""
            print(f"  {n['score']:6.1f}  {n['name']}{ratio}{mark}")
        if top and top["decisive"]:
            print(f"\nthis claim points decisively at {top['name']}. Measured on "
                  f"this store: when it fires, it is either the entry the claim "
                  f"restates or one the author linked to — never noise.")
            print(f"  extend it instead:  kb.py capture --extend {top['name']} <source>")
            print(f"  read it first:      kb.py show {top['name']}")

    if args.check:
        return
    if not args.type or not args.name:
        print("\nerror: --type and --name are required to write "
              "(or use --check to stop here)", file=sys.stderr)
        sys.exit(1)

    # Only the top neighbour is prefilled as a link: measured against the 132
    # hand-set links in this store, the top-ranked neighbour of an entry's body
    # is a link its author drew 70% of the time, precision that falls to 51% by
    # rank 3. The rest are printed above for the author to add, because a wrong
    # edge is not free — `candidates`, `consolidate` and the graph all read it.
    links = [top["name"]] if top else []
    dest = _scaffold_or_exit(
        entry_type=args.type, name=args.name, due=args.due,
        description=args.description or _first_sentence(passage),
        body=passage, links=links,
        source=_source_label(args.source),
    )
    print(f"\ncreated {dest.relative_to(ROOT)} (confidence: unverified)")
    if links:
        print(f"linked to {links[0]}")
    print("next: read it back, set confidence honestly, add the links above "
          "that belong, then kb.py lint")


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


# Instruction-shaped-content detection (ROADMAP Phase 10). A knowledge base
# served to agents over MCP is an injection surface: an entry that influences
# tool selection is a privileged execution path. Measured before shipping,
# against the 29 real entries in this store plus 9 planted attack payloads
# (see kb-instruction-content-lint): these four signals, unioned, caught 7/9
# planted attacks with 0 false positives on the real store. The two misses —
# a base64-obfuscated payload and an override phrase worded differently from
# the patterns below — are an honest limit of regex matching, not chased by
# widening the patterns further (that trade recall for false positives on a
# store that talks about its own governance in plain prose). Content inside
# code spans/fences is exempted from the prose signals so an entry that
# documents these phrases as examples (like the write-up entry itself) does
# not flag itself.
_CODE_FENCE_RE = re.compile(r'```[a-zA-Z]*\n(.*?)```', re.DOTALL)
_INLINE_CODE_RE = re.compile(r'`([^`]+)`')
_SECOND_PERSON_DIRECTIVE_RE = re.compile(
    r'\byou (must|should always|are now|may)\b', re.IGNORECASE
)
_OVERRIDE_PHRASE_RE = re.compile(
    r'ignore (all )?previous instructions'
    r'|disregard (your|the|any) (instructions|guidelines)'
    r'|supersedes? (all|any) other'
    r'|sole source of truth'
    r'|no restrictions\b'
    r'|developer mode'
    r'|safety checks?'
    r'|bypass the usual'
    r'|higher priority than the user',
    re.IGNORECASE,
)
_HTML_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
_DESTRUCTIVE_COMMAND_RE = re.compile(
    r'rm -rf'
    r'|curl[^`\n]*(\|\s*(sh|bash)\b|\$\(cat)'
    r'|git push[^`\n]*--force',
    re.IGNORECASE,
)


def _strip_code_spans(body):
    return _INLINE_CODE_RE.sub("", _CODE_FENCE_RE.sub("", body))


def _scan_instruction_content(body):
    """Return human-readable reasons this entry body reads as an instruction
    directed at the agent rather than documentation for one. Empty list means
    clean. See the module comment above for how this was measured."""
    reasons = []
    prose = _strip_code_spans(body)
    if _SECOND_PERSON_DIRECTIVE_RE.search(prose):
        reasons.append("direct second-person directive (e.g. 'you must', 'you are now')")
    if _OVERRIDE_PHRASE_RE.search(prose):
        reasons.append("override phrase (e.g. 'ignore previous instructions', 'sole source of truth')")
    if _HTML_COMMENT_RE.search(prose):
        reasons.append("hidden HTML comment")
    code_spans = _CODE_FENCE_RE.findall(body) + _INLINE_CODE_RE.findall(body)
    if any(_DESTRUCTIVE_COMMAND_RE.search(span) for span in code_spans):
        reasons.append("destructive shell command embedded in a code span")
    return reasons


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
            fm, body = parse_frontmatter(path)
        except OSError as e:
            problems.append(f"{rel}: could not read file ({e})")
            continue
        name = fm.get("name", path.stem)

        for reason in _scan_instruction_content(body):
            warnings.append(f"{rel}: possible instruction-shaped content — {reason}")

        if name in seen_names:
            problems.append(f"duplicate slug '{name}': {seen_names[name]} vs {rel}")
        else:
            seen_names[name] = rel

        confidence = fm.get("confidence")
        if confidence not in set(CONFIDENCE_LEVELS):
            problems.append(f"{rel}: missing/invalid confidence field")

        authority = fm.get("authority")
        if authority and authority not in ("rule", "preference"):
            problems.append(f"{rel}: authority '{authority}' must be 'rule' or 'preference' (or omitted)")

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

        archived = fm.get("archived")
        if archived:
            archived_names.add(name)
            try:
                datetime.date.fromisoformat(str(archived))
            except ValueError:
                problems.append(f"{rel}: archived is not a valid date: {archived!r}")

        if entry_type == "prospective":
            due = fm.get("due")
            if due:
                try:
                    due_date = datetime.date.fromisoformat(due)
                    # Archiving a spent reminder is how a prospective entry is
                    # meant to end, and its due date stays in the past forever
                    # after — so warning about it is a warning nothing can
                    # clear. Same reasoning as the freshness guards below;
                    # `triage` and `due` already skip archived entries.
                    if due_date < today and not archived:
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

    p_eval = sub.add_parser(
        "eval", help="score retrieval against the golden query set")
    p_eval.add_argument("--all", action="store_true",
                        help="list every query, not only the ones ranked wrong")
    p_eval.add_argument("--json", action="store_true", help="machine-readable output")
    p_eval.set_defaults(func=cmd_eval)

    p_show = sub.add_parser("show", help="print one entry")
    p_show.add_argument("name")
    p_show.set_defaults(func=cmd_show)

    p_history = sub.add_parser(
        "history", help="what one entry has said, and which revision changed it")
    p_history.add_argument("name")
    p_history.add_argument("--limit", type=int, default=0,
                           help="show only the most recent N revisions (0 for all)")
    p_history.add_argument("--json", action="store_true", help="machine-readable output")
    p_history.set_defaults(func=cmd_history)

    p_log = sub.add_parser(
        "log", help="what changed in the store, most recent first (reads .kb/log.md)")
    p_log.add_argument("--limit", type=int, default=20,
                       help="show only the most recent N records (0 for all; default 20)")
    p_log.add_argument("--type", choices=TYPES, help="only this memory type")
    p_log.add_argument("--action", help="only this action, e.g. created, verified, linked")
    p_log.add_argument("--name", help="only this entry's slug")
    p_log.add_argument("--json", action="store_true", help="machine-readable output")
    p_log.set_defaults(func=cmd_log)

    p_new = sub.add_parser("new", help="scaffold a new entry")
    p_new.add_argument("name")
    p_new.add_argument("--type", required=True, choices=TYPES)
    p_new.add_argument("--due", help="ISO date; required for --type prospective")
    p_new.set_defaults(func=cmd_new)

    p_capture = sub.add_parser(
        "capture",
        help="check a claim you have written against the store, then file it")
    p_capture.add_argument("source", nargs="?",
                           help="file holding the claim, or - for stdin (default)")
    p_capture.add_argument("--text", help="the claim itself, instead of a file")
    p_capture.add_argument("--type", choices=TYPES,
                           help="memory type; required unless --check or --extend")
    p_capture.add_argument("--name", help="slug for the new entry; "
                                          "required unless --check or --extend")
    p_capture.add_argument("--description",
                           help="one-line summary (default: the passage's first sentence)")
    p_capture.add_argument("--due", help="ISO date; required for --type prospective")
    p_capture.add_argument("--extend", metavar="NAME",
                           help="append the passage to this existing entry "
                                "instead of writing a near-twin")
    p_capture.add_argument("--check", action="store_true",
                           help="only report the nearest entries; write nothing")
    p_capture.add_argument("--json", action="store_true",
                           help="machine-readable view of the check")
    p_capture.set_defaults(func=cmd_capture)

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

    p_stats = sub.add_parser(
        "stats", help="what the store is made of — counts, graph, age, growth")
    p_stats.add_argument("--json", action="store_true", help="machine-readable output")
    p_stats.set_defaults(func=cmd_stats)

    p_triage = sub.add_parser("triage", help="queue of entries needing attention")
    p_triage.add_argument("--type", choices=TYPES, help="only this memory type")
    p_triage.add_argument("--reason", choices=sorted(TRIAGE_SEVERITY),
                          help="only entries flagged for this reason")
    p_triage.add_argument("--json", action="store_true", help="machine-readable output")
    p_triage.set_defaults(func=cmd_triage)

    p_due = sub.add_parser(
        "due", help="prospective entries whose due date has arrived or is approaching")
    p_due.add_argument("--within", type=_parse_within, metavar="Nd",
                       help="only entries due within N days, e.g. 14d "
                            "(overdue entries always show); default: all due dates")
    p_due.add_argument("--json", action="store_true", help="machine-readable output")
    p_due.set_defaults(func=cmd_due)

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
                        help="include pairs already settled on both axes")
    p_cand.add_argument("--json", action="store_true", help="machine-readable output")
    p_cand.set_defaults(func=cmd_candidates)

    p_cons = sub.add_parser(
        "consolidate",
        help="what the standing verdicts still owe — merges, missing links, "
             "restated passages")
    p_cons.add_argument("--only", choices=("merges", "missing_edges", "restatements"),
                        help="show one queue instead of all three")
    p_cons.add_argument("--margin", type=float, default=RESTATEMENT_MARGIN,
                        help="how far a passage's best entry must beat the "
                             f"runner-up (default {RESTATEMENT_MARGIN}); lower "
                             "trades more passages to read for more recall")
    p_cons.add_argument("--lines", type=int, default=3,
                        help="wrapped lines of each passage to show (default 3)")
    p_cons.add_argument("--json", action="store_true", help="machine-readable output")
    p_cons.set_defaults(func=cmd_consolidate)

    p_judge = sub.add_parser(
        "judge", help="record a judgement about one candidate pair")
    p_judge.add_argument("a")
    p_judge.add_argument("b")
    p_judge.add_argument("verdict", choices=VERDICTS)
    p_judge.add_argument("--agreement", choices=AGREEMENTS,
                         help="the other, independent question: do these two "
                              "entries disagree? omitting it leaves the pair "
                              "unexamined, not cleared")
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
