#!/usr/bin/env python3
"""Retrieval regression tests, run against the *real* store.

Every other suite here builds a throwaway KB, because it is testing tooling.
This one is testing the memory itself — whether the entries that exist answer
the questions somebody would actually ask — so a synthetic corpus would be
measuring nothing.

What these tests can see is itself measured (ROADMAP Phase 7): at this store
size the golden set detects gross breakage and is blind to parameter tuning.
The floors below are therefore set where the measurement supports them, well
under today's scores, and nothing here asserts a tuned constant. If you find
yourself adjusting a floor upward to lock in an improvement, don't — the
improvement is inside the noise band the phase measured.
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import kb  # noqa: E402

# Today: success@1 0.536, MRR 0.653, recall@3 0.750, recall@5 0.821 over 28
# queries — one query was retired on 2026-08-05 along with the entry it asked
# about (`holiday-autonomy-mandate`, archived once the mandate expired).
# The floors sit ~4 queries below that, which is the drift a growing store can
# produce without anything being wrong, and still far above a broken ranker
# (name-only scored 0.214 / 0.263 in the Phase 7 ablation).
FLOOR_SUCCESS_AT_1 = 0.40
FLOOR_MRR = 0.55
FLOOR_RECALL_AT_5 = 0.75
# A query that restates its entry's title tests the tokenizer, not retrieval.
MAX_TITLE_OVERLAP = 0.60


def name_only_ranker(docs):
    """The ranker with the entry bodies taken away.

    Used as a sensitivity check, not as a proposal: `rank` indexes name,
    description, body and metadata together, so scoring names alone is a
    faithful "retrieval is broken" signal rather than an artificial one.
    """
    stripped = [
        (t, path, fm, body,
         kb.tokenize(fm.get("name", path.stem).replace("-", " ")))
        for t, path, fm, body, _ in docs
    ]
    return lambda query: kb.rank(query, docs=stripped)


class GoldenSetTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.golden = kb.load_golden()
        cls.docs = kb.entry_documents()
        cls.report = kb.eval_report(golden=cls.golden, docs=cls.docs)
        cls.summary = cls.report["summary"]


class TestGoldenSetIsUsable(GoldenSetTestCase):
    def test_the_set_exists_and_is_big_enough_to_average(self):
        self.assertGreaterEqual(len(self.golden), 20, "golden set has shrunk")

    def test_every_expectation_names_a_real_entry(self):
        self.assertEqual(
            self.summary["unresolved"], [],
            "golden.json expects entries that no longer exist — rename or "
            "delete them, an unresolvable expectation is a permanent miss",
        )

    def test_no_query_appears_twice(self):
        queries = [g["query"] for g in self.golden]
        self.assertEqual(len(queries), len(set(queries)))

    def test_no_entry_quotes_a_golden_query(self):
        """The store documents itself, so a write-up can contaminate the set.

        The entry describing this fixture originally illustrated the rule by
        quoting a real query. That made the write-up the top hit for its own
        query, displacing the entry that should have answered it — recall@5
        fell from 0.862 to 0.793. Examples in entries must be invented.
        """
        for _, path, fm, body, _ in self.docs:
            haystack = " ".join(body.lower().split())
            for g in self.golden:
                self.assertNotIn(
                    " ".join(g["query"].lower().split()), haystack,
                    f"{fm.get('name', path.stem)} quotes the golden query "
                    f"{g['query']!r} — invent an example instead, a quoted "
                    f"query makes the quoting entry match it perfectly",
                )

    def test_no_query_restates_its_own_entry_title(self):
        """The property the whole set rests on.

        Queries generated from entry titles score 1.000 against every ranker
        measured in Phase 7 — including one that never looks at a body. Any
        drift toward the entry's own wording quietly turns a regression test
        into decoration, so it is asserted rather than trusted to a comment.
        """
        by_name = {fm.get("name", path.stem): fm
                   for _, path, fm, _, _ in self.docs}
        for g in self.golden:
            fm = by_name.get(g["expect"])
            if fm is None:
                continue
            title = set(kb.tokenize(fm.get("name", "").replace("-", " ")))
            shared = title & set(kb.tokenize(g["query"]))
            overlap = len(shared) / len(title) if title else 0.0
            self.assertLessEqual(
                overlap, MAX_TITLE_OVERLAP,
                f"query {g['query']!r} reuses {overlap:.0%} of the words in "
                f"{g['expect']!r} — reword the question, not the expectation",
            )


class TestRetrievalMeetsItsFloor(GoldenSetTestCase):
    def test_success_at_1(self):
        self.assertGreaterEqual(self.summary["success_at_1"], FLOOR_SUCCESS_AT_1,
                                self._diagnosis())

    def test_mean_reciprocal_rank(self):
        self.assertGreaterEqual(self.summary["mrr"], FLOOR_MRR, self._diagnosis())

    def test_recall_at_5(self):
        """What `kb.py context` actually hands back, so the metric that matters
        most as the store grows."""
        self.assertGreaterEqual(self.summary["recall_at_5"], FLOOR_RECALL_AT_5,
                                self._diagnosis())

    def _diagnosis(self):
        misses = [f"  #{r['rank'] or '-'} {r['query']!r} -> want {r['expect']}, "
                  f"got {', '.join(r['top'][:3])}"
                  for r in self.report["queries"] if r["rank"] != 1]
        return ("retrieval fell below its floor. Run `kb.py eval` for the "
                "full picture. Queries whose top hit is wrong:\n"
                + "\n".join(misses))


class TestTheSetCanStillFail(GoldenSetTestCase):
    """A golden set that passes for a broken ranker is decoration.

    This is the test that expires: as entries accumulate, a set written against
    28 of them stops discriminating long before it stops passing. When this
    fails, the fix is new queries, not a lower floor.
    """

    def test_a_ranker_that_ignores_entry_bodies_falls_below_the_floor(self):
        degraded = kb.eval_report(golden=self.golden, docs=self.docs,
                                  rank_fn=name_only_ranker(self.docs))["summary"]
        self.assertLess(
            degraded["success_at_1"], FLOOR_SUCCESS_AT_1,
            "the golden set no longer distinguishes real retrieval from "
            "title matching — add queries that need the body to answer",
        )
        self.assertLess(degraded["mrr"], FLOOR_MRR)

    def test_the_live_ranker_beats_the_degraded_one_by_a_wide_margin(self):
        degraded = kb.eval_report(golden=self.golden, docs=self.docs,
                                  rank_fn=name_only_ranker(self.docs))["summary"]
        self.assertGreater(self.summary["mrr"] - degraded["mrr"], 0.20)


if __name__ == "__main__":
    unittest.main()
