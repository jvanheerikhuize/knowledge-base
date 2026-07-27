#!/usr/bin/env python3
"""Stdlib unittest suite for scripts/kb.py, run against a throwaway temp KB.

Each test copies kb.py plus the real template/schema into a fresh temp
directory (so kb.py's module-level ROOT/MEMORY resolve there, not into the
real repo) and drives it as a subprocess, the same way a user would.
"""
import datetime
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class KbTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        (self.root / "scripts").mkdir()
        (self.root / ".kb" / "templates").mkdir(parents=True)
        (self.root / ".kb" / "schema").mkdir(parents=True)
        shutil.copy(REPO_ROOT / "scripts" / "kb.py", self.root / "scripts" / "kb.py")
        shutil.copy(
            REPO_ROOT / ".kb" / "templates" / "entry.template.md",
            self.root / ".kb" / "templates" / "entry.template.md",
        )
        shutil.copy(
            REPO_ROOT / ".kb" / "schema" / "entry.schema.json",
            self.root / ".kb" / "schema" / "entry.schema.json",
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def run_kb(self, *args):
        return subprocess.run(
            [sys.executable, str(self.root / "scripts" / "kb.py"), *args],
            cwd=self.root,
            capture_output=True,
            text=True,
        )

    def entry_path(self, entry_type, slug):
        return self.root / "memory" / entry_type / f"{slug}.md"

    def edit_frontmatter(self, entry_type, slug, **fields):
        path = self.entry_path(entry_type, slug)
        text = path.read_text()
        for key, value in fields.items():
            if key == "links":
                rendered = "[" + ", ".join(value) + "]"
                text = text.replace("links: []", f"links: {rendered}")
            else:
                import re

                text = re.sub(rf"^{key}:.*$", f"{key}: {value}", text, flags=re.MULTILINE)
        path.write_text(text)


class TestNew(KbTestCase):
    def test_creates_entry_with_slug_and_type(self):
        result = self.run_kb("new", "My Cool Fact", "--type", "semantic")
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.entry_path("semantic", "my-cool-fact")
        self.assertTrue(path.is_file())
        text = path.read_text()
        self.assertIn("name: my-cool-fact", text)
        self.assertIn("type: semantic", text)

    def test_rejects_invalid_type(self):
        result = self.run_kb("new", "thing", "--type", "bogus")
        self.assertNotEqual(result.returncode, 0)

    def test_rejects_duplicate_entry(self):
        self.run_kb("new", "dup-entry", "--type", "semantic")
        result = self.run_kb("new", "dup-entry", "--type", "semantic")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stderr)


class TestListAndSearch(KbTestCase):
    def test_list_empty(self):
        result = self.run_kb("list")
        self.assertEqual(result.returncode, 0)
        self.assertIn("no entries yet", result.stdout)

    def test_list_shows_created_entry(self):
        self.run_kb("new", "widget-fact", "--type", "semantic")
        result = self.run_kb("list")
        self.assertIn("widget-fact", result.stdout)

    def test_list_filters_by_type(self):
        self.run_kb("new", "a-semantic", "--type", "semantic")
        self.run_kb("new", "a-procedure", "--type", "procedural")
        result = self.run_kb("list", "--type", "procedural")
        self.assertIn("a-procedure", result.stdout)
        self.assertNotIn("a-semantic", result.stdout)

    def test_search_finds_keyword_in_body(self):
        self.run_kb("new", "searchable-entry", "--type", "semantic")
        path = self.entry_path("semantic", "searchable-entry")
        text = path.read_text().replace("Body content", "unicorn-flavored content")
        path.write_text(text)
        result = self.run_kb("search", "unicorn-flavored")
        self.assertIn("searchable-entry", result.stdout)

    def test_search_no_matches(self):
        self.run_kb("new", "boring-entry", "--type", "semantic")
        result = self.run_kb("search", "nonexistent-keyword-xyz")
        self.assertIn("no matches", result.stdout)


class RankingTestCase(KbTestCase):
    """A small corpus with known term distribution, for ranking assertions."""

    def make(self, entry_type, slug, body, **fields):
        self.run_kb("new", slug, "--type", entry_type,
                    *(["--due", "2099-01-01"] if entry_type == "prospective" else []))
        path = self.entry_path(entry_type, slug)
        text = path.read_text()
        text = text[: text.index("---", 3) + 4] + body + "\n"
        path.write_text(text)
        if fields:
            self.edit_frontmatter(entry_type, slug, **fields)
        return path


class TestSearchRanking(RankingTestCase):
    def test_more_mentions_rank_higher(self):
        self.make("semantic", "dense", "kafka kafka kafka partitions and offsets")
        self.make("semantic", "sparse", "kafka is mentioned once here, among much "
                  "other unrelated prose about printers and paper trays")
        out = self.run_kb("search", "kafka").stdout
        self.assertLess(out.index("dense"), out.index("sparse"))

    def test_a_name_match_outranks_a_body_match(self):
        self.make("semantic", "kafka-retention", "durable log storage policy")
        self.make("semantic", "unrelated-note", "we once evaluated kafka briefly")
        out = self.run_kb("search", "kafka").stdout
        self.assertLess(out.index("kafka-retention"), out.index("unrelated-note"))

    def test_output_carries_a_score_and_the_matched_terms(self):
        self.make("semantic", "scored", "postgres vacuum tuning")
        payload = json.loads(self.run_kb("search", "vacuum", "--json").stdout)
        self.assertEqual(payload[0]["name"], "scored")
        self.assertGreater(payload[0]["score"], 0)
        self.assertEqual(payload[0]["matched"], ["vacuum"])

    def test_limit_caps_the_result_list(self):
        for i in range(4):
            self.make("semantic", f"note-{i}", "shared topic term")
        payload = json.loads(self.run_kb("search", "topic", "--limit", "2", "--json").stdout)
        self.assertEqual(len(payload), 2)

    def test_type_filter_restricts_the_corpus(self):
        self.make("semantic", "a-fact", "deployment rollback")
        self.make("procedural", "a-runbook", "deployment rollback")
        payload = json.loads(
            self.run_kb("search", "deployment", "--type", "procedural", "--json").stdout)
        self.assertEqual([h["name"] for h in payload], ["a-runbook"])

    def test_recent_episodic_outranks_an_old_one(self):
        today = datetime.date.today()
        old = (today - datetime.timedelta(days=900)).isoformat()
        self.make("episodic", "old-run", "migration attempt notes",
                  created=old, last_verified=old)
        self.make("episodic", "new-run", "migration attempt notes",
                  created=today.isoformat(), last_verified=today.isoformat())
        out = self.run_kb("search", "migration").stdout
        self.assertLess(out.index("new-run"), out.index("old-run"))

    def test_confidence_breaks_a_tie(self):
        self.make("semantic", "trusted-one", "identical wording here",
                  confidence="verified")
        self.make("semantic", "shaky-one", "identical wording here",
                  confidence="low")
        out = self.run_kb("search", "identical wording").stdout
        self.assertLess(out.index("trusted-one"), out.index("shaky-one"))

    def test_a_query_of_only_noise_matches_nothing(self):
        self.make("semantic", "some-entry", "real content")
        self.assertIn("no matches", self.run_kb("search", "a").stdout)


class TestContext(RankingTestCase):
    def test_pack_names_the_task_and_carries_provenance(self):
        self.make("semantic", "cache-policy", "we cache for one hour",
                  confidence="verified")
        out = self.run_kb("context", "cache policy").stdout
        self.assertIn("# Context for: cache policy", out)
        self.assertIn("cache-policy", out)
        self.assertIn("memory/semantic/cache-policy.md", out)
        self.assertIn("confidence: verified", out)

    def test_pack_never_exceeds_its_budget(self):
        for i in range(6):
            self.make("semantic", f"long-{i}", "budget " + ("filler words " * 200))
        for budget in (100, 300, 900):
            pack = json.loads(
                self.run_kb("context", "budget", "--budget", str(budget), "--json").stdout)
            self.assertLessEqual(pack["tokens"], budget, budget)

    def test_a_straddling_entry_is_trimmed_not_dropped(self):
        self.make("semantic", "big-one", "trimmable " + ("filler words " * 400))
        pack = json.loads(
            self.run_kb("context", "trimmable", "--budget", "120", "--json").stdout)
        self.assertEqual(pack["trimmed"], ["big-one"])
        self.assertEqual([e["name"] for e in pack["entries"]], ["big-one"])

    def test_episodic_is_excluded_by_default_and_opt_in(self):
        self.make("episodic", "the-run", "rollout observations")
        self.assertNotIn("the-run", self.run_kb("context", "rollout").stdout)
        self.assertIn("the-run", self.run_kb("context", "rollout", "--episodic").stdout)

    def test_no_matches_still_produces_a_valid_pack(self):
        self.make("semantic", "unrelated", "nothing to see")
        pack = json.loads(self.run_kb("context", "quasar-telemetry", "--json").stdout)
        self.assertEqual(pack["entries"], [])
        self.assertIn("no matches", pack["text"])


class TestShow(KbTestCase):
    def test_show_prints_entry(self):
        self.run_kb("new", "shown-entry", "--type", "semantic")
        result = self.run_kb("show", "shown-entry")
        self.assertEqual(result.returncode, 0)
        self.assertIn("name: shown-entry", result.stdout)

    def test_show_missing_entry_exits_nonzero(self):
        result = self.run_kb("show", "does-not-exist")
        self.assertNotEqual(result.returncode, 0)


class TestLint(KbTestCase):
    def test_lint_clean_kb(self):
        self.run_kb("new", "clean-entry", "--type", "semantic")
        self.run_kb("new", "clean-entry-linker", "--type", "semantic")
        self.edit_frontmatter("semantic", "clean-entry", links=["clean-entry-linker"])
        self.edit_frontmatter("semantic", "clean-entry-linker", links=["clean-entry"])
        result = self.run_kb("lint")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("lint clean", result.stdout)

    def test_lint_catches_missing_required_field(self):
        self.run_kb("new", "missing-field", "--type", "semantic")
        path = self.entry_path("semantic", "missing-field")
        text = path.read_text().replace("description: one-line summary\n", "")
        path.write_text(text)
        result = self.run_kb("lint")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing required field 'description'", result.stdout)

    def test_lint_catches_duplicate_slug(self):
        self.run_kb("new", "dup-slug", "--type", "semantic")
        self.run_kb("new", "dup-slug", "--type", "episodic")
        # cmd_new refuses same-type duplicates, so hand-craft a same-slug
        # entry under a different type to trigger the cross-type duplicate check.
        other = self.entry_path("episodic", "dup-slug")
        other.write_text(self.entry_path("semantic", "dup-slug").read_text())
        result = self.run_kb("lint")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("duplicate slug", result.stdout)

    def test_lint_catches_dangling_link(self):
        self.run_kb("new", "linker", "--type", "semantic")
        self.edit_frontmatter("semantic", "linker", links=["nonexistent-target"])
        result = self.run_kb("lint")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dangling link", result.stdout)

    def test_lint_catches_invalid_type_enum(self):
        self.run_kb("new", "bad-type", "--type", "semantic")
        self.edit_frontmatter("semantic", "bad-type", type="not-a-real-type")
        result = self.run_kb("lint")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("is not one of", result.stdout)

    def test_lint_catches_invalid_name_pattern(self):
        self.run_kb("new", "renamed-later", "--type", "semantic")
        self.edit_frontmatter("semantic", "renamed-later", name="Not_Kebab_Case")
        result = self.run_kb("lint")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match required pattern", result.stdout)

    def test_lint_warns_on_stale_entry_but_does_not_fail(self):
        self.run_kb("new", "stale-entry", "--type", "semantic")
        self.edit_frontmatter(
            "semantic", "stale-entry", confidence="high", last_verified="2020-01-01"
        )
        result = self.run_kb("lint")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("[warning]", result.stdout)
        self.assertIn("stale", result.stdout)

    def test_lint_strict_treats_staleness_warning_as_fatal(self):
        self.run_kb("new", "strict-stale", "--type", "semantic")
        self.edit_frontmatter(
            "semantic", "strict-stale", confidence="high", last_verified="2020-01-01"
        )
        result = self.run_kb("lint", "--strict")
        self.assertNotEqual(result.returncode, 0)

    def test_lint_catches_type_folder_mismatch(self):
        self.run_kb("new", "mismatched", "--type", "semantic")
        self.edit_frontmatter("semantic", "mismatched", type="episodic")
        result = self.run_kb("lint")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match its folder", result.stdout)

    def test_lint_warns_on_overdue_prospective(self):
        self.run_kb("new", "overdue-task", "--type", "prospective", "--due", "2020-01-01")
        result = self.run_kb("lint")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("overdue", result.stdout)

    def test_lint_does_not_warn_on_future_due(self):
        self.run_kb("new", "future-task", "--type", "prospective", "--due", "2099-01-01")
        result = self.run_kb("lint")
        self.assertNotIn("overdue", result.stdout)

    def test_lint_warns_on_orphan_entry(self):
        self.run_kb("new", "lonely-entry", "--type", "semantic")
        result = self.run_kb("lint")
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("orphan entry", result.stdout)


class TestNewDueAndLog(KbTestCase):
    def test_prospective_requires_due(self):
        result = self.run_kb("new", "no-due-task", "--type", "prospective")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--due is required", result.stderr)

    def test_prospective_with_due_writes_date(self):
        self.run_kb("new", "due-task", "--type", "prospective", "--due", "2030-06-01")
        text = self.entry_path("prospective", "due-task").read_text()
        self.assertIn("due: 2030-06-01", text)

    def test_non_prospective_strips_due_line(self):
        self.run_kb("new", "no-due-needed", "--type", "semantic")
        text = self.entry_path("semantic", "no-due-needed").read_text()
        self.assertNotIn("due:", text)
        self.assertNotIn("\n\n\n", text)
        self.assertIn("links: []\n---\n", text)

    def test_invalid_due_date_rejected(self):
        result = self.run_kb("new", "bad-due", "--type", "prospective", "--due", "not-a-date")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a valid date", result.stderr)

    def test_new_appends_to_log(self):
        self.run_kb("new", "logged-entry", "--type", "semantic")
        log_path = self.root / ".kb" / "log.md"
        self.assertTrue(log_path.is_file())
        self.assertIn("logged-entry", log_path.read_text())

    def test_new_appends_multiple_log_lines(self):
        self.run_kb("new", "first-entry", "--type", "semantic")
        self.run_kb("new", "second-entry", "--type", "semantic")
        log_text = (self.root / ".kb" / "log.md").read_text()
        self.assertIn("first-entry", log_text)
        self.assertIn("second-entry", log_text)


class TestTriage(KbTestCase):
    def test_clean_kb_reports_nothing(self):
        self.run_kb("new", "a-entry", "--type", "semantic")
        self.run_kb("new", "b-entry", "--type", "semantic")
        self.run_kb("link", "a-entry", "b-entry")
        self.run_kb("link", "b-entry", "a-entry")
        result = self.run_kb("triage")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("triage clean", result.stdout)

    def test_flags_stale_and_orphan_entries(self):
        self.run_kb("new", "old-entry", "--type", "semantic")
        self.edit_frontmatter("semantic", "old-entry", last_verified="2000-01-01")
        result = self.run_kb("triage")
        self.assertIn("stale", result.stdout)
        self.assertIn("orphan", result.stdout)
        self.assertIn("unlinked", result.stdout)

    def test_flags_overdue_prospective(self):
        self.run_kb("new", "past-task", "--type", "prospective", "--due", "2000-01-01")
        result = self.run_kb("triage")
        self.assertIn("overdue", result.stdout)

    def test_json_output_is_parseable_and_sorted_by_severity(self):
        self.run_kb("new", "due-task", "--type", "prospective", "--due", "2000-01-01")
        self.run_kb("new", "lonely", "--type", "semantic")
        result = self.run_kb("triage", "--json")
        report = json.loads(result.stdout)
        self.assertEqual(len(report), 2)
        self.assertEqual(report[0]["name"], "due-task")
        self.assertLessEqual(report[0]["severity"], report[1]["severity"])

    def test_filters_by_type_and_reason(self):
        self.run_kb("new", "due-task", "--type", "prospective", "--due", "2000-01-01")
        self.run_kb("new", "lonely", "--type", "semantic")
        by_type = json.loads(self.run_kb("triage", "--type", "semantic", "--json").stdout)
        self.assertEqual([r["name"] for r in by_type], ["lonely"])
        by_reason = json.loads(self.run_kb("triage", "--reason", "overdue", "--json").stdout)
        self.assertEqual([r["name"] for r in by_reason], ["due-task"])


class TestStatus(KbTestCase):
    """`status` covers every entry exactly once; `triage` covers only problems."""

    def _clean_pair(self):
        self.run_kb("new", "a-entry", "--type", "semantic")
        self.run_kb("new", "b-entry", "--type", "semantic")
        self.run_kb("link", "a-entry", "b-entry")
        self.run_kb("link", "b-entry", "a-entry")
        self.run_kb("verify", "a-entry", "--confidence", "verified")
        self.run_kb("verify", "b-entry", "--confidence", "verified")

    def test_every_entry_appears_exactly_once(self):
        self._clean_pair()
        self.run_kb("new", "lonely", "--type", "semantic")
        report = json.loads(self.run_kb("status", "--json").stdout)
        names = [r["name"] for r in report]
        self.assertEqual(sorted(names), ["a-entry", "b-entry", "lonely"])
        self.assertEqual(len(names), len(set(names)))

    def test_clean_entries_are_current(self):
        self._clean_pair()
        report = json.loads(self.run_kb("status", "--json").stdout)
        self.assertEqual({r["status"] for r in report}, {"current"})

    def test_worst_status_wins(self):
        # Overdue *and* orphaned; overdue is the more urgent of the two.
        self.run_kb("new", "past-task", "--type", "prospective", "--due", "2000-01-01")
        report = json.loads(self.run_kb("status", "--json").stdout)
        self.assertEqual(report[0]["status"], "overdue")
        self.assertIn("orphan", [r["code"] for r in report[0]["reasons"]])

    def test_orphan_is_isolated_and_stale_beats_it(self):
        self.run_kb("new", "lonely", "--type", "semantic")
        report = json.loads(self.run_kb("status", "--json").stdout)
        self.assertEqual(report[0]["status"], "isolated")
        self.edit_frontmatter("semantic", "lonely", last_verified="2000-01-01")
        report = json.loads(self.run_kb("status", "--json").stdout)
        self.assertEqual(report[0]["status"], "stale")

    def test_low_confidence_is_provisional(self):
        self._clean_pair()
        self.run_kb("set", "a-entry", "confidence", "medium")
        report = json.loads(self.run_kb("status", "--json").stdout)
        by_name = {r["name"]: r for r in report}
        self.assertEqual(by_name["a-entry"]["status"], "provisional")
        self.assertEqual(by_name["b-entry"]["status"], "current")

    def test_every_record_names_the_command_that_moves_it(self):
        self._clean_pair()
        self.run_kb("set", "a-entry", "confidence", "low")
        report = json.loads(self.run_kb("status", "--json").stdout)
        for record in report:
            self.assertTrue(record["action"])
            self.assertNotIn("<name>", record["action"])
        action = next(r["action"] for r in report if r["name"] == "a-entry")
        self.assertIn("a-entry", action)

    def test_review_by_is_ninety_days_after_last_verified(self):
        self._clean_pair()
        self.edit_frontmatter("semantic", "a-entry", last_verified="2020-01-01")
        report = json.loads(self.run_kb("status", "--json").stdout)
        record = next(r for r in report if r["name"] == "a-entry")
        self.assertEqual(record["review_by"], "2020-03-31")

    def test_unparseable_date_is_broken(self):
        self._clean_pair()
        self.edit_frontmatter("semantic", "a-entry", last_verified="soon")
        report = json.loads(self.run_kb("status", "--json").stdout)
        record = next(r for r in report if r["name"] == "a-entry")
        self.assertEqual(record["status"], "broken")
        self.assertIsNone(record["age_days"])

    def test_filters_by_type_and_status(self):
        self._clean_pair()
        self.run_kb("new", "past-task", "--type", "prospective", "--due", "2000-01-01")
        by_type = json.loads(self.run_kb("status", "--type", "prospective", "--json").stdout)
        self.assertEqual([r["name"] for r in by_type], ["past-task"])
        by_status = json.loads(self.run_kb("status", "--status", "current", "--json").stdout)
        self.assertEqual(sorted(r["name"] for r in by_status), ["a-entry", "b-entry"])

    def test_legend_explains_every_status(self):
        result = self.run_kb("status", "--legend")
        self.assertEqual(result.returncode, 0, result.stderr)
        for key in ("broken", "overdue", "stale", "unverified",
                    "provisional", "isolated", "ageing", "current"):
            self.assertIn(key, result.stdout)


class TestVerify(KbTestCase):
    def test_stamps_today_and_optional_confidence(self):
        self.run_kb("new", "stale-fact", "--type", "semantic")
        self.edit_frontmatter("semantic", "stale-fact", last_verified="2000-01-01")
        result = self.run_kb("verify", "stale-fact", "--confidence", "high")
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.entry_path("semantic", "stale-fact").read_text()
        self.assertIn(f"last_verified: {datetime.date.today().isoformat()}", text)
        self.assertIn("confidence: high", text)

    def test_unknown_entry_fails(self):
        result = self.run_kb("verify", "nope")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no entry named", result.stderr)

    def test_body_survives_the_rewrite(self):
        self.run_kb("new", "keep-body", "--type", "semantic")
        path = self.entry_path("semantic", "keep-body")
        before = path.read_text().split("---\n", 2)[2]
        self.run_kb("verify", "keep-body")
        self.assertEqual(path.read_text().split("---\n", 2)[2], before)


class TestSet(KbTestCase):
    def test_sets_an_arbitrary_field(self):
        self.run_kb("new", "some-fact", "--type", "semantic")
        result = self.run_kb("set", "some-fact", "description", "a better summary")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("description: a better summary",
                      self.entry_path("semantic", "some-fact").read_text())

    def test_adds_a_field_that_was_absent(self):
        self.run_kb("new", "some-fact", "--type", "semantic")
        path = self.entry_path("semantic", "some-fact")
        path.write_text(path.read_text().replace("source: where this came from\n", ""))
        self.run_kb("set", "some-fact", "source", "an-origin")
        self.assertIn("source: an-origin", path.read_text())

    def test_refuses_identity_fields(self):
        self.run_kb("new", "some-fact", "--type", "semantic")
        for field in ("name", "type"):
            result = self.run_kb("set", "some-fact", field, "whatever")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing", result.stderr)

    def test_validates_dates_and_confidence(self):
        self.run_kb("new", "some-fact", "--type", "semantic")
        self.assertNotEqual(self.run_kb("set", "some-fact", "created", "nope").returncode, 0)
        self.assertNotEqual(
            self.run_kb("set", "some-fact", "confidence", "sorta").returncode, 0)


class TestLink(KbTestCase):
    def setUp(self):
        super().setUp()
        self.run_kb("new", "from-entry", "--type", "semantic")
        self.run_kb("new", "to-entry", "--type", "semantic")

    def test_adds_and_removes_a_link(self):
        self.run_kb("link", "from-entry", "to-entry")
        path = self.entry_path("semantic", "from-entry")
        self.assertIn("links: [to-entry]", path.read_text())
        self.run_kb("link", "from-entry", "to-entry", "--remove")
        self.assertIn("links: []", path.read_text())

    def test_refuses_dangling_target(self):
        result = self.run_kb("link", "from-entry", "ghost")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dangling", result.stderr)

    def test_refuses_self_link_and_is_idempotent(self):
        self.assertNotEqual(
            self.run_kb("link", "from-entry", "from-entry").returncode, 0)
        self.run_kb("link", "from-entry", "to-entry")
        result = self.run_kb("link", "from-entry", "to-entry")
        self.assertEqual(result.returncode, 0)
        self.assertIn("already links", result.stdout)
        self.assertIn("links: [to-entry]", self.entry_path("semantic", "from-entry").read_text())

    def test_linked_kb_still_lints_clean(self):
        self.run_kb("link", "from-entry", "to-entry")
        self.run_kb("link", "to-entry", "from-entry")
        self.assertEqual(self.run_kb("lint").returncode, 0)


class TestRm(KbTestCase):
    def setUp(self):
        super().setUp()
        self.run_kb("new", "doomed", "--type", "semantic")
        self.run_kb("new", "referrer", "--type", "semantic")

    def test_deletes_an_unreferenced_entry(self):
        result = self.run_kb("rm", "doomed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.entry_path("semantic", "doomed").exists())

    def test_refuses_when_referenced(self):
        self.run_kb("link", "referrer", "doomed")
        result = self.run_kb("rm", "doomed")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("still linked from", result.stderr)
        self.assertTrue(self.entry_path("semantic", "doomed").exists())

    def test_force_strips_inbound_links_leaving_no_dangling_refs(self):
        self.run_kb("link", "referrer", "doomed")
        result = self.run_kb("rm", "doomed", "--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.entry_path("semantic", "doomed").exists())
        self.assertIn("links: []", self.entry_path("semantic", "referrer").read_text())
        self.assertEqual(self.run_kb("lint").returncode, 0)


class TestMutationLog(KbTestCase):
    def test_mutations_are_recorded(self):
        self.run_kb("new", "tracked", "--type", "semantic")
        self.run_kb("verify", "tracked")
        self.run_kb("set", "tracked", "description", "changed")
        self.run_kb("rm", "tracked")
        log = (self.root / ".kb" / "log.md").read_text()
        for action in ("created", "verified", "updated", "deleted"):
            self.assertIn(action, log)


class TestWriteBody(KbTestCase):
    """write_body() backs browser edits, so it must never touch frontmatter."""

    def load(self):
        """Import kb.py rooted at the temp KB, without leaving it cached for
        other test modules that import the real one."""
        cached = sys.modules.pop("kb", None)
        sys.path.insert(0, str(self.root / "scripts"))
        try:
            import kb
        finally:
            sys.path.pop(0)
            sys.modules.pop("kb", None)
            if cached is not None:
                sys.modules["kb"] = cached
        return kb

    def test_replaces_body_and_preserves_frontmatter(self):
        self.run_kb("new", "body-target", "--type", "semantic")
        path = self.entry_path("semantic", "body-target")
        kb = self.load()
        kb.write_body(path, "Completely new prose.")
        text = path.read_text()
        self.assertIn("name: body-target", text)
        self.assertIn("type: semantic", text)
        self.assertIn("Completely new prose.", text)
        self.assertNotIn("Body content", text)

    def test_empty_body_leaves_a_valid_entry(self):
        self.run_kb("new", "emptied", "--type", "semantic")
        path = self.entry_path("semantic", "emptied")
        kb = self.load()
        kb.write_body(path, "   ")
        self.assertTrue(path.read_text().startswith("---\n"))
        self.assertEqual(path.read_text().count("---"), 2)

    def test_rejects_a_file_without_frontmatter(self):
        path = self.root / "memory" / "semantic"
        path.mkdir(parents=True, exist_ok=True)
        stray = path / "no-frontmatter.md"
        stray.write_text("just prose\n")
        kb = self.load()
        with self.assertRaises(ValueError):
            kb.write_body(stray, "x")


if __name__ == "__main__":
    unittest.main()
