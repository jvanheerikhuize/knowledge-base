#!/usr/bin/env python3
"""The `archived` axis: one declared policy per store-scanning function.

Three commands have shipped with a missing archived filter — `dupes`
(2026-07-29), `eval` (2026-08-05), `lint` (2026-08-06) — and all three were
found by *reading* the code, never by a failing test.

`kb-archived-is-a-filter-commands-forget` explains that as an archived-blind
test corpus: only one entry in 34 is archived, so the archived branch of a
scanner is a branch no fixture reaches. **Measured on 2026-08-07, that is not
what is wrong.** Mutation test: delete each of the 13 places kb.py consults
`archived`, one at a time, and run the whole suite against each. **12 of 13
mutants die**, most within a test written specifically for the archived case.
The corpus defends very nearly every archived guard that exists. (The one
survivor was `lint`'s unverified-age warning, whose `and not archived` clause
no test pinned; `test_lint_does_not_raise_an_attention_warning_on_the_archived
_entry` below now kills it.)

Both facts hold at once because they are about different code: **you cannot
mutate a line that is not there.** All three bugs were *absent* guards, not
broken ones, and a test corpus — however thorough, however diverse its
fixtures — can only exercise code that was written. Coverage of the archived
branch was never the missing ingredient; every command that had the branch had
a test for it. What was missing is anything that notices a scanner which never
asked the question at all.

So the repair is not more coverage. It is an enumeration that fails on
*absence*: discover every function that scans the store, and require each one
to name its policy. That is a check no amount of fixture diversity substitutes
for, and it is the only shape that would have failed on all three bugs the day
they were written.

Two halves:

* `TestScannerRegistryIsComplete` discovers every function that scans the store
  and fails if one is missing from `SCANNER_POLICY`. A new scanner cannot be
  added without stating, in one word, what archived means to it. That is the
  half the three bugs needed: each was a scanner whose author never had to
  answer the question.
* `TestArchivedPolicyHolds` drives each declared policy through the CLI against
  a store that actually contains an archived entry, so the declaration is
  backed by behaviour rather than by a comment.

Scope, stated honestly: discovery covers functions that call `iter_entries()`
directly, plus non-`cmd_` functions in kb.py that consume one of those. The
`cmd_*` wrappers and the MCP tool handlers are deliberately out — they inherit
whatever the library function they call decided, and pinning the policy at the
library layer is what stops it being re-decided per caller.
"""
import ast
import datetime
import json
import unittest
from pathlib import Path

from test_kb import REPO_ROOT, KbTestCase

# --- the policies ----------------------------------------------------------
# EXCLUDES   archived entries must not appear in this function's output
# CLASSIFIES they appear, labelled as archived — the label is the point
# INCLUDES   they appear unfiltered, on purpose; the reason is the value
EXCLUDES = "excludes"
CLASSIFIES = "classifies"
INCLUDES = "includes"

SCANNER_POLICY = {
    # --- retrieval and pair-finding: archived is retired, so it is gone -----
    ("kb.py", "dupe_pairs"): (
        EXCLUDES, "a retired entry is not a live duplicate of anything"),
    ("kb.py", "_candidate_docs"): (
        EXCLUDES, "the judgement queue is about entries still in play"),
    ("kb.py", "neighbour_pairs"): (
        EXCLUDES, "inherits _candidate_docs"),
    ("kb.py", "candidate_pairs"): (
        EXCLUDES, "inherits _candidate_docs"),
    ("kb.py", "standing_contradictions"): (
        EXCLUDES, "inherits _candidate_docs"),
    ("kb.py", "restatements"): (
        EXCLUDES, "inherits _candidate_docs"),
    ("kb.py", "nearest_entries"): (
        EXCLUDES, "inherits _candidate_docs"),
    ("kb.py", "consolidation_report"): (
        EXCLUDES, "inherits _candidate_docs"),
    ("kb.py", "rank"): (
        EXCLUDES, "leaving the retrieval set is what archiving means; "
                  "--archived/include_archived is the explicit opt-in"),
    ("kb.py", "eval_report"): (
        EXCLUDES, "an archived expectation is unanswerable, so scoring it "
                  "is a guaranteed miss forever"),
    ("kb.py", "context_pack"): (
        EXCLUDES, "inherits rank — a context pack is what an agent acts on, "
                  "so a retired claim reaching it is the worst case of all"),
    ("kb.py", "capture_report"): (
        EXCLUDES, "inherits nearest_entries; a new claim is checked against "
                  "what the store still stands behind"),

    # --- attention queues: archiving already answered "what about this" ----
    ("kb.py", "triage_report"): (
        EXCLUDES, "continuing to flag a retired entry makes the queue "
                  "un-clearable"),
    ("kb.py", "due_report"): (
        EXCLUDES, "archiving is how a spent prospective entry ends"),
    ("kb.py", "review_forecast"): (
        EXCLUDES, "a retired entry is never coming up for review"),
    ("kb.py", "cmd_lint"): (
        EXCLUDES, "the three attention warnings (stale, unverified, overdue) "
                  "only; schema and date-validity problems stay unconditional, "
                  "because bad data is bad data whether or not it is retired"),

    # --- inventories: the label is the product ------------------------------
    ("kb.py", "status_report"): (
        CLASSIFIES, "`archived` is a status, and it short-circuits the rest"),
    ("kb.py", "stats_report"): (
        CLASSIFIES, "counted as its own bucket, so `entries` stays the total"),
    ("build_site.py", "collect"): (
        CLASSIFIES, "the site renders archived entries with an archived badge; "
                    "the store is a public record, not a retrieval set"),
    ("build_site.py", "build"): (
        CLASSIFIES, "inherits collect and status_report"),
    ("build_site.py", "main"): (
        CLASSIFIES, "inherits build; the CLI entry point decides nothing"),
    ("mcp_server.py", "list_resources"): (
        CLASSIFIES, "a resource listing is a discovery surface an agent picks "
                    "from, so a retired entry must be readable but must not "
                    "read as current — listed, and labelled archived"),

    # --- whole-store access: retirement is not deletion --------------------
    ("kb.py", "entry_documents"): (
        INCLUDES, "the corpus every ranker reads; filtering here would make "
                  "search --archived unimplementable, so rank filters instead. "
                  "Any new consumer must filter for itself — this is exactly "
                  "how eval_report got it wrong on 2026-08-05"),
    ("kb.py", "resolve"): (
        INCLUDES, "an archived entry is still readable by name"),
    ("kb.py", "_require"): (
        INCLUDES, "inherits resolve; every by-name command must still reach "
                  "a retired entry, or `archive --undo` could not work"),
    ("kb.py", "cmd_list"): (
        INCLUDES, "an inventory of files on disk, not of retrievable claims"),
    ("kb.py", "cmd_show"): (
        INCLUDES, "reading one entry by name; see resolve"),
    ("kb.py", "cmd_rm"): (
        INCLUDES, "an archived entry still links, so it is still a referrer "
                  "that would dangle"),
    ("serve.py", "_all"): (
        INCLUDES, "the local edit server exists to edit files, including "
                  "retired ones"),
    ("mcp_server.py", "_all_entries"): (
        INCLUDES, "link-target validation must accept archived entries, since "
                  "they stay in the graph"),
    ("mcp_server.py", "tool_propose_update"): (
        INCLUDES, "inherits _all_entries; it must also be able to address an "
                  "archived entry in order to un-archive it"),
    ("serve.py", "_known_names"): (
        INCLUDES, "inherits _all; the same link-target rule as the MCP server"),
    ("serve.py", "api_update"): (
        INCLUDES, "inherits _known_names; editing a retired entry is allowed"),
    ("serve.py", "api_delete"): (
        INCLUDES, "inherits _all; an archived entry is still a referrer whose "
                  "link would dangle — see cmd_rm"),
}

SCRIPTS = ("kb.py", "build_site.py", "serve.py", "mcp_server.py")


def discover_scanners():
    """Every function that reads the whole store, found mechanically.

    Direct: calls `iter_entries()`. Derived: a non-`cmd_` function in kb.py
    that calls a direct scanner (or another derived one). Returns
    {(script, function name)}.
    """
    found = set()
    for script in SCRIPTS:
        src = (REPO_ROOT / "scripts" / script).read_text(encoding="utf-8")
        tree = ast.parse(src)
        funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
        plain, qualified = {}, {}
        for node in funcs:
            plain[node.name] = {
                c.func.id for c in ast.walk(node)
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
            }
            qualified[node.name] = {
                c.func.attr for c in ast.walk(node)
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
            }
        calls = plain

        # Attribute calls count only for spotting `kb.iter_entries()` in the
        # other three scripts. They must NOT feed the closure below: a method
        # call like `pathlib.Path(x).resolve()` is indistinguishable by name
        # from kb's own `resolve()`, and matching on it pulled `_source_label`
        # in as a store scanner when it never touches the store.
        direct = {n for n in calls
                  if "iter_entries" in plain[n] | qualified[n]}
        # Transitive closure over the library layer, in every script — not
        # just kb.py. Scoping the closure to kb.py was this module's own first
        # version of the bug it exists to catch: `mcp_server.list_resources`
        # consumes `_all_entries` and so decides the archived question, but a
        # kb.py-only closure could not see it.
        # `cmd_*` wrappers stay out unless they scan directly: they inherit
        # their policy from the function they call, and re-declaring it per
        # caller is the duplication this registry exists to avoid.
        scanners = set(direct)
        changed = True
        while changed:
            changed = False
            for name, called in calls.items():
                if name in scanners or name.startswith("cmd_"):
                    continue
                if called & scanners:
                    scanners.add(name)
                    changed = True
        found |= {(script, n) for n in scanners}
    return found


class TestScannerRegistryIsComplete(unittest.TestCase):
    """The half that fails on the *next* scanner, not on the last three."""

    def test_every_store_scanner_declares_an_archived_policy(self):
        discovered = discover_scanners()
        declared = set(SCANNER_POLICY)
        missing = discovered - declared
        self.assertEqual(
            missing, set(),
            "these functions scan the store but declare no archived policy in "
            "SCANNER_POLICY — decide what `archived` means to each, add it to "
            "the registry, and cover it in TestArchivedPolicyHolds:\n  "
            + "\n  ".join(sorted(f"{s}:{n}" for s, n in missing)),
        )

    def test_the_registry_has_no_stale_rows(self):
        discovered = discover_scanners()
        stale = set(SCANNER_POLICY) - discovered
        self.assertEqual(
            stale, set(),
            "SCANNER_POLICY names functions that no longer scan the store — "
            "a row nobody can violate reads as coverage that is not there:\n  "
            + "\n  ".join(sorted(f"{s}:{n}" for s, n in stale)),
        )

    def test_every_policy_is_one_of_the_three_and_carries_a_reason(self):
        for key, value in SCANNER_POLICY.items():
            with self.subTest(scanner=key):
                policy, reason = value
                self.assertIn(policy, (EXCLUDES, CLASSIFIES, INCLUDES))
                self.assertGreater(
                    len(reason), 20,
                    f"{key}: a policy without a reason is a policy nobody can "
                    "re-check")

    def test_discovery_finds_the_three_functions_that_shipped_the_bug(self):
        # A discovery rule that missed any of these would be a rule that
        # could not have caught the defects this module exists for.
        discovered = discover_scanners()
        for name in ("dupe_pairs", "eval_report", "cmd_lint"):
            self.assertIn(("kb.py", name), discovered)


class ArchivedAxisTestCase(KbTestCase):
    """A store whose archived entry is otherwise indistinguishable.

    `kept` and `retired` share their subject wording so that any similarity- or
    rank-driven scanner must consider the pair, and both are old enough and
    unverified enough to trip every attention warning. The only difference
    between them is that one is archived.
    """

    SHARED = ("the retrieval set and the archived set are two different "
              "sets of entries in this store")

    def setUp(self):
        super().setUp()
        old = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
        for slug in ("kept", "retired"):
            self.run_kb("new", slug, "--type", "semantic")
            self.edit_frontmatter("semantic", slug, description=self.SHARED,
                                  last_verified=old, confidence="unverified")
            path = self.entry_path("semantic", slug)
            path.write_text(path.read_text().rstrip() + "\n\n" + self.SHARED + "\n")
        # Linked both ways so neither is an orphan for reasons unrelated to
        # archiving.
        self.run_kb("link", "kept", "retired")
        self.run_kb("link", "retired", "kept")
        self.run_kb("archive", "retired")

    def json_kb(self, *args):
        result = self.run_kb(*args, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)


class TestArchivedPolicyHolds(ArchivedAxisTestCase):
    """Each EXCLUDES / CLASSIFIES row, driven through the CLI."""

    def assert_excluded(self, blob, where):
        self.assertNotIn("retired", json.dumps(blob),
                         f"{where}: an archived entry reached output that "
                         "declares EXCLUDES")

    # --- EXCLUDES ---------------------------------------------------------

    def test_search_excludes_the_archived_entry(self):
        hits = self.json_kb("search", self.SHARED)
        names = [h["name"] for h in hits]
        self.assertIn("kept", names)
        self.assertNotIn("retired", names)

    def test_search_can_still_opt_in(self):
        result = self.run_kb("search", self.SHARED, "--archived", "--json")
        self.assertIn("retired", [h["name"] for h in json.loads(result.stdout)])

    def test_dupes_excludes_the_archived_entry(self):
        self.assert_excluded(self.json_kb("dupes"), "dupes")

    def test_candidates_excludes_the_archived_entry(self):
        self.assert_excluded(self.json_kb("candidates"), "candidates")

    def test_consolidate_excludes_the_archived_entry(self):
        self.assert_excluded(self.json_kb("consolidate"), "consolidate")

    def test_triage_excludes_the_archived_entry(self):
        rows = self.json_kb("triage")
        self.assertIn("kept", [r["name"] for r in rows])
        self.assertNotIn("retired", [r["name"] for r in rows])

    def test_lint_does_not_raise_an_attention_warning_on_the_archived_entry(self):
        result = self.run_kb("lint")
        for line in result.stdout.splitlines():
            if "retired" in line:
                self.assertNotIn("stale", line)
                self.assertNotIn("unverified for", line)
                self.assertNotIn("overdue", line)

    def test_strict_lint_is_clean_with_only_an_archived_entry_at_fault(self):
        # `kept` is deliberately as stale as `retired`, so remove it and the
        # only remaining offender is the archived one.
        self.run_kb("rm", "kept", "--force")
        result = self.run_kb("lint", "--strict")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_due_excludes_an_archived_prospective_entry(self):
        self.run_kb("new", "spent", "--type", "prospective", "--due", "2020-01-01")
        self.run_kb("archive", "spent")
        self.assert_excluded(self.json_kb("due", "--within", "9999"), "due")

    def test_the_review_forecast_excludes_the_archived_entry(self):
        stats = self.json_kb("stats")
        forecast = json.dumps(stats.get("review_forecast", stats))
        self.assertNotIn("retired", forecast)

    # --- CLASSIFIES -------------------------------------------------------

    def test_status_labels_the_archived_entry_rather_than_dropping_it(self):
        rows = self.json_kb("status")
        by_name = {r["name"]: r for r in rows}
        self.assertIn("retired", by_name)
        self.assertEqual(by_name["retired"]["status"], "archived")
        self.assertNotEqual(by_name["kept"]["status"], "archived")

    def test_stats_counts_the_archived_entry_in_its_own_bucket(self):
        stats = self.json_kb("stats")
        self.assertEqual(stats["archived"], 1)
        self.assertEqual(stats["entries"], 2)

    # --- INCLUDES ---------------------------------------------------------

    def test_an_archived_entry_is_still_readable_by_name(self):
        result = self.run_kb("show", "retired")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("name: retired", result.stdout)

    def test_an_archived_entry_still_appears_in_list(self):
        self.assertIn("retired", self.run_kb("list").stdout)

    def test_removing_an_entry_is_refused_because_an_archived_entry_links_to_it(self):
        # `retired` links to `kept`, so deleting `kept` would dangle that link.
        # Retirement is not a licence to leave a dangling edge behind: the
        # entry left the retrieval set, not the graph.
        result = self.run_kb("rm", "kept")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("retired", result.stderr)


if __name__ == "__main__":
    unittest.main()
