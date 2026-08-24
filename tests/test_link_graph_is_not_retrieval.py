#!/usr/bin/env python3
"""The link graph is not a retrieval structure, and the store now says so.

Until 2026-08-24 `kb.py status --legend` and `memory/AGENT.md` both described
an `isolated` entry as one that "will not be found by following the graph".
Nothing follows the graph. `rank` scores BM25 plus type, confidence and
recency; `context_pack` fills a budget from that ranking; neither reads
`links`, and neither does any MCP tool. The only consumers of an edge are the
site's "Links out"/"Linked from" panes, `consolidate`'s missing-edge queue,
`lint`'s orphan warning, and `rm`'s refusal to delete a linked entry.

That mattered because the wording sits inside a status model whose whole
vocabulary is retrieval (`archived` is defined as "retired from retrieval"),
so it read as a retrieval consequence — and made linking look like owed work
with a payoff nothing delivered.

Measured before rewording it (ROADMAP Phase 24). The graph is not noise: 114
of 190 edges are not among either endpoint's three nearest neighbours by
similarity, and an edge to the top hit raises the odds that an entry is the
right answer 4.2x (10/144 against 12/723, Fisher exact one-sided p = 0.0013).
It is simply too coarse for the pack. One hop names 7.76 entries where the
pack holds 2.43, so promoting a neighbour is right 6.9% of the time against
26.3% for the rank-2 entry it displaces, and every one-hop expansion measured
scored at or below the baseline at the shipped budget.

So there are two claims to keep honest, and one test each:

* `TestRetrievalIgnoresTheGraph` — behavioural. Strip every `links:` value and
  retrieval is bit-identical. This is the executable form of the corrected
  wording: the day a ranker does follow the graph, this fails, and whoever
  makes it fail has to rewrite the legend in the same commit.
* `TestTheLegendDoesNotPromiseRetrieval` — the wording itself, in both places
  it is published, so the two cannot drift apart again.

`TestNeighbourhoodAgainstPack` covers the number that decides when any of this
should be revisited.
"""
import copy
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import kb  # noqa: E402

AGENT_MD = kb.MEMORY / "AGENT.md"


def _stripped(docs):
    """The same documents with every `links:` value emptied."""
    out = []
    for t, path, fm, body, tokens in docs:
        fm = copy.deepcopy(fm)
        fm["links"] = []
        out.append((t, path, fm, body, tokens))
    return out


class TestRetrievalIgnoresTheGraph(unittest.TestCase):
    """No ranking or packing decision reads an edge. Run against the real store."""

    @classmethod
    def setUpClass(cls):
        cls.docs = kb.entry_documents()
        cls.blind = _stripped(cls.docs)
        cls.queries = [g["query"] for g in kb.load_golden()]
        if not cls.queries:
            cls.queries = ["how does the search decide what comes back first"]

    def test_ranking_is_identical_without_any_links(self):
        for query in self.queries:
            with self.subTest(query=query):
                a = [(h["name"], h["score"]) for h in kb.rank(query, docs=self.docs)]
                b = [(h["name"], h["score"]) for h in kb.rank(query, docs=self.blind)]
                self.assertEqual(a, b)

    def test_the_context_pack_is_identical_without_any_links(self):
        for query in self.queries:
            with self.subTest(query=query):
                a = kb.context_pack(query, docs=self.docs)
                b = kb.context_pack(query, docs=self.blind)
                self.assertEqual(a["text"], b["text"])
                self.assertEqual(a["reach"], b["reach"])

    def test_every_entry_stays_retrievable_with_no_edges_at_all(self):
        """The old wording's claim, tested directly.

        `isolated` used to say the entry "will not be found by following the
        graph". In a store where every entry is isolated, each one is still
        found by its own words — and found at the same rank as before. That is
        what makes the old sentence wrong rather than merely imprecise.
        """
        for _, path, fm, body, _ in self.docs:
            if kb.is_archived(fm):
                continue
            query = fm.get("description") or body[:200]
            name = fm.get("name", path.stem)
            with self.subTest(entry=name):
                blind = kb.rank(query, docs=self.blind)
                names = [h["name"] for h in blind]
                self.assertIn(name, names, "an entry with no edges left "
                                           "cannot find itself")
                self.assertEqual(
                    names.index(name),
                    [h["name"] for h in kb.rank(query, docs=self.docs)].index(name),
                    "stripping the graph moved this entry's own rank")


class TestTheLegendDoesNotPromiseRetrieval(unittest.TestCase):
    """The wording, in both places it ships."""

    def _isolated_meaning(self):
        for status in kb.STATUS_MODEL:
            if status["key"] == "isolated":
                return status["meaning"]
        self.fail("no 'isolated' status in STATUS_MODEL")

    def test_the_cli_legend_says_retrieval_is_unaffected(self):
        meaning = self._isolated_meaning().lower()
        self.assertIn("no ranker follows the graph", meaning)
        for wrong in ("will not be found", "unreachable", "cannot be found"):
            self.assertNotIn(wrong, meaning)

    def test_agent_md_says_the_same_thing(self):
        rows = [line for line in AGENT_MD.read_text(encoding="utf-8").splitlines()
                if line.startswith("| `isolated`")]
        self.assertEqual(len(rows), 1, "expected exactly one isolated row")
        row = rows[0].lower()
        self.assertIn("no ranker follows the graph", row)
        for wrong in ("unreachable by following the graph", "will not be found"):
            self.assertNotIn(wrong, row)


class TestNeighbourhoodAgainstPack(unittest.TestCase):
    """`mean_link_neighbourhood` and the ratio `eval` reports beside the pack."""

    def _docs(self, spec):
        """(name, links, archived) triples as rank()-shaped documents."""
        docs = []
        for name, links, archived in spec:
            fm = {"name": name, "links": list(links)}
            if archived:
                fm["archived"] = "2026-08-24"
            docs.append(("semantic", Path(f"{name}.md"), fm, "body", ["body"]))
        return docs

    def test_an_edge_counts_for_both_ends_however_it_was_written(self):
        one_way = self._docs([("a", ["b"], False), ("b", [], False)])
        both_ways = self._docs([("a", ["b"], False), ("b", ["a"], False)])
        self.assertEqual(kb.mean_link_neighbourhood(one_way), 1.0)
        self.assertEqual(kb.mean_link_neighbourhood(both_ways), 1.0)

    def test_a_dangling_link_is_not_a_hop(self):
        docs = self._docs([("a", ["gone"], False), ("b", [], False)])
        self.assertEqual(kb.mean_link_neighbourhood(docs), 0.0)

    def test_archived_entries_are_out_of_the_graph_as_they_are_out_of_retrieval(self):
        docs = self._docs([("a", ["b"], False), ("b", [], True)])
        self.assertEqual(kb.mean_link_neighbourhood(docs), 0.0)

    def test_an_empty_store_has_no_neighbourhood(self):
        self.assertEqual(kb.mean_link_neighbourhood([]), 0.0)

    def test_eval_reports_the_ratio_against_the_pack(self):
        summary = kb.eval_report()["summary"]
        self.assertIn("link_neighbourhood", summary)
        self.assertIn("neighbourhood_over_pack", summary)
        self.assertAlmostEqual(
            summary["neighbourhood_over_pack"],
            summary["link_neighbourhood"] / summary["mean_pack_entries"],
            places=1,
        )

    def test_the_measured_limit_is_not_a_gate(self):
        """Reported, never enforced — the same call `budget_bound` and
        `judgement_load` make. `kb.py eval` must not exit non-zero because the
        ratio is high; today's store is well past the limit and the suite has
        to stay green."""
        summary = kb.eval_report()["summary"]
        self.assertGreater(summary["neighbourhood_over_pack"],
                           kb.NEIGHBOURHOOD_PACK_RATIO_LIMIT,
                           "if the store has fallen back under the limit, this "
                           "test is stale — re-read ROADMAP Phase 24 rather "
                           "than deleting it")


if __name__ == "__main__":
    unittest.main()
