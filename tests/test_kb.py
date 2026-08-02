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

    def test_readme_and_template_files_in_a_type_folder_are_not_entries(self):
        self.run_kb("new", "real-entry", "--type", "semantic")
        folder = self.entry_path("semantic", "real-entry").parent
        (folder / "README.md").write_text("# semantic\n\nnot an entry")
        (folder / "scratch.template.md").write_text("---\nname: scratch\n---\n")
        result = self.run_kb("list")
        self.assertIn("real-entry", result.stdout)
        self.assertNotIn("README", result.stdout)
        self.assertNotIn("scratch", result.stdout)
        self.assertEqual(self.run_kb("lint").returncode, 0, self.run_kb("lint").stdout)

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

    def test_limit_caps_how_many_ranked_hits_are_considered(self):
        for i in range(4):
            self.make("semantic", f"widget-{i}", "widget " * (4 - i))
        pack = json.loads(
            self.run_kb("context", "widget", "--limit", "2", "--json").stdout)
        self.assertEqual(len(pack["entries"]), 2)
        self.assertEqual({e["name"] for e in pack["entries"]},
                         {"widget-0", "widget-1"})


class TestShow(KbTestCase):
    def test_show_prints_entry(self):
        self.run_kb("new", "shown-entry", "--type", "semantic")
        result = self.run_kb("show", "shown-entry")
        self.assertEqual(result.returncode, 0)
        self.assertIn("name: shown-entry", result.stdout)

    def test_show_missing_entry_exits_nonzero(self):
        result = self.run_kb("show", "does-not-exist")
        self.assertNotEqual(result.returncode, 0)


class TestHistory(KbTestCase):
    """`history` reads git, so these tests build a real repo in the temp store.

    The classification is the part worth pinning: `verify` and `link` touch an
    entry far more often than an author does, and the command is only useful if
    those revisions stay visually out of the way of the ones that changed a
    claim.
    """

    def git(self, *args):
        result = subprocess.run(
            ["git", "-c", "user.email=t@example.com", "-c", "user.name=Test", *args],
            cwd=self.root, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def init_repo(self):
        self.git("init", "-q", "-b", "main")

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def test_without_a_git_repo_it_says_so_instead_of_crashing(self):
        self.run_kb("new", "lonely-fact", "--type", "semantic")
        result = self.run_kb("history", "lonely-fact")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not a git repository", result.stderr)

    def test_an_uncommitted_entry_reports_no_history_yet(self):
        self.init_repo()
        self.run_kb("new", "brand-new", "--type", "semantic")
        result = self.run_kb("history", "brand-new")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("never been committed", result.stdout)

    def test_an_untracked_entry_in_a_live_repo_reports_no_history_yet(self):
        self.init_repo()
        self.run_kb("new", "committed-fact", "--type", "semantic")
        self.commit("add committed-fact")
        self.run_kb("new", "untracked-fact", "--type", "semantic")
        result = self.run_kb("history", "untracked-fact")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("never been committed", result.stdout)

    def test_missing_entry_exits_nonzero(self):
        self.init_repo()
        result = self.run_kb("history", "does-not-exist")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no entry named", result.stderr)

    def test_first_revision_is_written_and_quotes_the_claim(self):
        self.init_repo()
        self.run_kb("new", "first-claim", "--type", "semantic")
        self.edit_frontmatter("semantic", "first-claim", description="the original claim")
        self.commit("add first-claim")
        result = self.run_kb("history", "first-claim")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("written", result.stdout)
        self.assertIn("the original claim", result.stdout)

    def test_a_verify_only_revision_is_not_reported_as_an_edit(self):
        self.init_repo()
        self.run_kb("new", "steady-fact", "--type", "semantic")
        self.commit("add steady-fact")
        self.run_kb("verify", "steady-fact", "--confidence", "high")
        self.commit("verify steady-fact")

        history = json.loads(self.run_kb("history", "steady-fact", "--json").stdout)
        changes = [r["change"] for r in history["revisions"]]
        self.assertEqual(changes, ["created", "metadata"])

    def test_a_changed_description_is_reported_as_a_changed_claim(self):
        self.init_repo()
        self.run_kb("new", "moving-fact", "--type", "semantic")
        self.edit_frontmatter("semantic", "moving-fact", description="eight statuses")
        self.commit("add moving-fact")
        self.edit_frontmatter("semantic", "moving-fact", description="ten statuses")
        self.commit("correct moving-fact")

        result = self.run_kb("history", "moving-fact")
        self.assertIn("claim changed", result.stdout)
        # the superseded wording is the whole point: it is nowhere else.
        self.assertIn("eight statuses", result.stdout)
        self.assertIn("the one-line claim has been rewritten 1 time", result.stdout)

    def test_a_body_rewrite_under_an_unchanged_claim_is_reported_as_an_edit(self):
        self.init_repo()
        self.run_kb("new", "reworded-fact", "--type", "semantic")
        self.commit("add reworded-fact")
        path = self.entry_path("semantic", "reworded-fact")
        path.write_text(path.read_text() + "\nA new paragraph of prose.\n")
        self.commit("expand reworded-fact")

        history = json.loads(self.run_kb("history", "reworded-fact", "--json").stdout)
        self.assertEqual([r["change"] for r in history["revisions"]], ["created", "body"])

    def test_limit_keeps_the_most_recent_revisions(self):
        self.init_repo()
        self.run_kb("new", "busy-fact", "--type", "semantic")
        self.commit("add busy-fact")
        for n in range(3):
            self.edit_frontmatter("semantic", "busy-fact", description=f"claim {n}")
            self.commit(f"revise busy-fact {n}")

        full = json.loads(self.run_kb("history", "busy-fact", "--json").stdout)
        limited = json.loads(
            self.run_kb("history", "busy-fact", "--limit", "2", "--json").stdout)
        self.assertEqual(len(full["revisions"]), 4)
        self.assertEqual(len(limited["revisions"]), 2)
        self.assertEqual(limited["revisions"], full["revisions"][-2:])

    def test_json_carries_the_path_and_the_shallow_flag(self):
        self.init_repo()
        self.run_kb("new", "described-fact", "--type", "semantic")
        self.commit("add described-fact")
        history = json.loads(self.run_kb("history", "described-fact", "--json").stdout)
        self.assertEqual(history["name"], "described-fact")
        self.assertEqual(history["type"], "semantic")
        self.assertEqual(history["path"], "memory/semantic/described-fact.md")
        self.assertFalse(history["shallow"])
        self.assertEqual(history["revisions"][0]["change"], "created")


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

    def test_new_appends_multiple_log_lines(self):
        self.run_kb("new", "first-entry", "--type", "semantic")
        self.run_kb("new", "second-entry", "--type", "semantic")
        log_path = self.root / ".kb" / "log.md"
        self.assertTrue(log_path.is_file())
        log_text = log_path.read_text()
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


class TestDue(KbTestCase):
    def _iso(self, days_from_today):
        return (datetime.date.today() + datetime.timedelta(days=days_from_today)).isoformat()

    def test_no_prospective_entries_reports_nothing_due(self):
        self.run_kb("new", "a-entry", "--type", "semantic")
        result = self.run_kb("due")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("nothing due", result.stdout)

    def test_lists_overdue_and_upcoming_sorted_by_due_date(self):
        self.run_kb("new", "far-off", "--type", "prospective", "--due", self._iso(30))
        self.run_kb("new", "past-due", "--type", "prospective", "--due", self._iso(-5))
        result = self.run_kb("due", "--json")
        rows = json.loads(result.stdout)
        self.assertEqual([r["name"] for r in rows], ["past-due", "far-off"])
        self.assertTrue(rows[0]["overdue"])
        self.assertFalse(rows[1]["overdue"])

    def test_within_excludes_entries_beyond_the_window(self):
        self.run_kb("new", "soon", "--type", "prospective", "--due", self._iso(5))
        self.run_kb("new", "later", "--type", "prospective", "--due", self._iso(30))
        result = self.run_kb("due", "--within", "14d", "--json")
        rows = json.loads(result.stdout)
        self.assertEqual([r["name"] for r in rows], ["soon"])

    def test_within_still_shows_overdue_entries(self):
        self.run_kb("new", "long-overdue", "--type", "prospective", "--due", self._iso(-100))
        result = self.run_kb("due", "--within", "14d", "--json")
        rows = json.loads(result.stdout)
        self.assertEqual([r["name"] for r in rows], ["long-overdue"])

    def test_within_accepts_bare_integer(self):
        self.run_kb("new", "soon", "--type", "prospective", "--due", self._iso(5))
        result = self.run_kb("due", "--within", "14", "--json")
        rows = json.loads(result.stdout)
        self.assertEqual([r["name"] for r in rows], ["soon"])

    def test_within_rejects_garbage(self):
        result = self.run_kb("due", "--within", "not-a-number")
        self.assertNotEqual(result.returncode, 0)

    def test_ignores_non_prospective_and_archived_and_undated(self):
        self.run_kb("new", "no-due-date", "--type", "prospective", "--due", self._iso(5))
        # strip the due line to simulate a prospective entry without one
        path = self.entry_path("prospective", "no-due-date")
        text = path.read_text()
        text = "\n".join(line for line in text.splitlines(keepends=True) if not line.startswith("due:"))
        path.write_text(text)
        self.run_kb("new", "archived-due", "--type", "prospective", "--due", self._iso(-1))
        self.run_kb("archive", "archived-due")
        result = self.run_kb("due", "--json")
        rows = json.loads(result.stdout)
        self.assertEqual(rows, [])

    def test_unparseable_due_date_is_skipped_not_crashed(self):
        self.run_kb("new", "bogus-date", "--type", "prospective", "--due", "2030-01-01")
        self.edit_frontmatter("prospective", "bogus-date", due="not-a-date")
        result = self.run_kb("due", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual(rows, [])


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

    def test_refuses_links_because_it_would_write_a_bare_string_not_a_list(self):
        self.run_kb("new", "some-fact", "--type", "semantic")
        result = self.run_kb("set", "some-fact", "links", "some-other-entry")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing", result.stderr)
        self.assertNotIn("links: some-other-entry",
                          self.entry_path("semantic", "some-fact").read_text())

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

    def test_deleting_from_a_mixed_type_store_logs_its_own_type(self):
        """Regression: cmd_rm's referrer scan iterates (type, path) pairs and
        must not let that loop variable overwrite the deleted entry's own
        type before the log line is written."""
        self.run_kb("new", "semantic-victim", "--type", "semantic")
        self.run_kb("new", "an-episode", "--type", "episodic")
        self.run_kb("rm", "semantic-victim")
        log = (self.root / ".kb" / "log.md").read_text()
        self.assertIn("semantic/semantic-victim.md", log)
        self.assertNotIn("episodic/semantic-victim.md", log)


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


class TestArchive(KbTestCase):
    """Archiving retires an entry from retrieval without losing it."""

    def setUp(self):
        super().setUp()
        self.run_kb("new", "kept-fact", "--type", "semantic")
        self.run_kb("new", "retired-fact", "--type", "semantic")
        for slug in ("kept-fact", "retired-fact"):
            self.run_kb("set", slug, "description", "shared subject matter")

    def test_archive_stamps_a_date_and_leaves_the_file_in_place(self):
        result = self.run_kb("archive", "retired-fact")
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.entry_path("semantic", "retired-fact")
        self.assertTrue(path.is_file())
        self.assertRegex(path.read_text(), r"archived: \d{4}-\d{2}-\d{2}")

    def test_archived_entries_drop_out_of_search(self):
        self.run_kb("archive", "retired-fact")
        hits = json.loads(self.run_kb("search", "shared subject", "--json").stdout)
        names = [h["name"] for h in hits]
        self.assertIn("kept-fact", names)
        self.assertNotIn("retired-fact", names)

    def test_archived_entries_can_still_be_searched_on_request(self):
        self.run_kb("archive", "retired-fact")
        hits = json.loads(
            self.run_kb("search", "shared subject", "--archived", "--json").stdout)
        names = [h["name"] for h in hits]
        self.assertIn("retired-fact", names)
        self.assertTrue(next(h for h in hits if h["name"] == "retired-fact")["archived"])

    def test_archived_entries_stay_readable(self):
        self.run_kb("archive", "retired-fact")
        result = self.run_kb("show", "retired-fact")
        self.assertEqual(result.returncode, 0)
        self.assertIn("name: retired-fact", result.stdout)

    def test_archived_entries_leave_the_triage_queue(self):
        self.edit_frontmatter("semantic", "retired-fact", last_verified="2000-01-01")
        before = json.loads(self.run_kb("triage", "--json").stdout)
        self.assertIn("retired-fact", [r["name"] for r in before])
        self.run_kb("archive", "retired-fact")
        after = json.loads(self.run_kb("triage", "--json").stdout)
        self.assertNotIn("retired-fact", [r["name"] for r in after])

    def test_status_still_accounts_for_archived_entries(self):
        self.run_kb("archive", "retired-fact")
        report = json.loads(self.run_kb("status", "--json").stdout)
        row = next(r for r in report if r["name"] == "retired-fact")
        self.assertEqual(row["status"], "archived")
        self.assertIn("retired-fact", [r["name"] for r in report])

    def test_lint_stops_nagging_about_an_archived_entry(self):
        self.edit_frontmatter("semantic", "retired-fact", last_verified="2000-01-01")
        self.run_kb("archive", "retired-fact")
        out = self.run_kb("lint").stdout
        self.assertNotIn("retired-fact.md: stale", out)
        self.assertNotIn("retired-fact.md: orphan", out)

    def test_undo_puts_it_back_in_the_retrieval_set(self):
        self.run_kb("archive", "retired-fact")
        result = self.run_kb("archive", "retired-fact", "--undo")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("archived:", self.entry_path("semantic", "retired-fact").read_text())
        hits = json.loads(self.run_kb("search", "shared subject", "--json").stdout)
        self.assertIn("retired-fact", [h["name"] for h in hits])

    def test_undo_on_a_live_entry_fails(self):
        result = self.run_kb("archive", "kept-fact", "--undo")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not archived", result.stderr)

    def test_archiving_twice_is_a_no_op(self):
        self.run_kb("archive", "retired-fact")
        first = self.entry_path("semantic", "retired-fact").read_text()
        result = self.run_kb("archive", "retired-fact")
        self.assertEqual(result.returncode, 0)
        self.assertIn("already archived", result.stdout)
        self.assertEqual(first, self.entry_path("semantic", "retired-fact").read_text())

    def test_archiving_is_recorded_in_the_mutation_log(self):
        self.run_kb("archive", "retired-fact")
        self.run_kb("archive", "retired-fact", "--undo")
        log = (self.root / ".kb" / "log.md").read_text()
        self.assertIn("archived `semantic/retired-fact.md`", log)
        self.assertIn("unarchived `semantic/retired-fact.md`", log)

    def test_an_unparseable_archived_date_is_a_lint_error(self):
        self.run_kb("archive", "retired-fact")
        self.edit_frontmatter("semantic", "retired-fact", archived="soon")
        result = self.run_kb("lint")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("archived is not a valid date", result.stdout)


class TestDupes(KbTestCase):
    """Near-verbatim detection: it must fire on copied text and stay quiet
    on entries that merely share a subject. The second half is the hard one,
    and the reason the default threshold is where it is."""

    PROSE_A = (
        "The knowledge base stores every memory as a markdown file with a "
        "small block of YAML frontmatter at the top. There is no database and "
        "no vector store anywhere in the design, and git is the only durable "
        "write path that the system relies on for its history."
    )
    # Same subject, no shared phrasing — this is what must NOT be flagged.
    PROSE_B = (
        "Each note here lives on disk as ordinary text, carrying a short "
        "header of structured fields. Nothing relational is involved, no "
        "embedding index exists, and version control alone provides the "
        "lasting record of how things changed over time."
    )

    def write_body(self, slug, prose, entry_type="semantic"):
        path = self.entry_path(entry_type, slug)
        head, _, _ = path.read_text().partition("---\n")[2].partition("\n---\n")
        path.write_text(f"---\n{head}\n---\n\n{prose}\n")

    def setUp(self):
        super().setUp()
        for slug in ("original-entry", "copied-entry", "paraphrased-entry"):
            self.run_kb("new", slug, "--type", "semantic")
        self.write_body("original-entry", self.PROSE_A)
        self.write_body("copied-entry", self.PROSE_A)
        self.write_body("paraphrased-entry", self.PROSE_B)

    def dupes(self, *args):
        return json.loads(self.run_kb("dupes", "--json", *args).stdout)

    def pair_names(self, report):
        return {frozenset((p["a"], p["b"])) for p in report["pairs"]}

    def test_a_copied_entry_is_flagged(self):
        pairs = self.pair_names(self.dupes())
        self.assertIn(frozenset(("original-entry", "copied-entry")), pairs)

    def test_a_copy_scores_at_the_top_of_the_scale(self):
        report = self.dupes()
        pair = next(p for p in report["pairs"]
                    if {p["a"], p["b"]} == {"original-entry", "copied-entry"})
        self.assertGreater(pair["jaccard"], 0.9)
        self.assertGreater(pair["containment"], 0.9)

    def test_a_paraphrase_is_not_flagged(self):
        pairs = self.pair_names(self.dupes())
        self.assertNotIn(frozenset(("original-entry", "paraphrased-entry")), pairs)

    def test_a_clean_store_reports_nothing(self):
        self.write_body("copied-entry", self.PROSE_B.replace("note", "record"))
        self.run_kb("rm", "paraphrased-entry")
        self.assertEqual(self.dupes()["pairs"], [])

    def test_containment_catches_an_entry_wholly_inside_another(self):
        self.write_body("copied-entry", self.PROSE_A + " " + self.PROSE_B)
        pair = next(p for p in self.dupes()["pairs"]
                    if {p["a"], p["b"]} == {"original-entry", "copied-entry"})
        self.assertGreater(pair["containment"], 0.9)
        self.assertLess(pair["jaccard"], pair["containment"])

    def test_the_threshold_is_adjustable(self):
        loose = self.dupes("--threshold", "0.001")
        strict = self.dupes("--threshold", "0.99")
        self.assertGreaterEqual(len(loose["pairs"]), len(strict["pairs"]))

    def test_short_entries_are_reported_rather_than_silently_skipped(self):
        self.run_kb("new", "stub-entry", "--type", "semantic")
        self.write_body("stub-entry", "Too short to judge.")
        self.assertIn("stub-entry", self.dupes()["too_short"])

    def test_existing_links_between_a_pair_are_surfaced(self):
        self.run_kb("link", "original-entry", "copied-entry")
        pair = next(p for p in self.dupes()["pairs"]
                    if {p["a"], p["b"]} == {"original-entry", "copied-entry"})
        self.assertTrue(pair["linked"])

    def test_human_output_names_its_own_limit(self):
        out = self.run_kb("dupes").stdout
        self.assertIn("not the same claim written twice", out)

    def test_an_archived_copy_is_not_flagged(self):
        self.run_kb("archive", "copied-entry")
        pairs = self.pair_names(self.dupes())
        self.assertNotIn(frozenset(("original-entry", "copied-entry")), pairs)


class TestCandidates(KbTestCase):
    """The other half of duplicate detection: the pair `dupes` is built to miss.

    `dupes` is precision-tuned and asserts duplicates. `candidates` is
    recall-tuned and asserts nothing — it hands an agent a short list to read.
    The load-bearing test here is the exact inverse of
    TestDupes.test_a_paraphrase_is_not_flagged: the pair that `dupes` must stay
    quiet about is the pair `candidates` must surface.
    """

    CLAIM = TestDupes.PROSE_A
    RESTATEMENT = TestDupes.PROSE_B

    # Filler, so the store is big enough that nearest-neighbour selection is
    # actually choosing between things. Each must clear MIN_CANDIDATE_TOKENS.
    FILLER = {
        "tides": "The moon pulls the ocean into a bulge that follows it around "
                 "the planet, and a second bulge forms on the far side where "
                 "the pull is weakest, so most coastlines see two high waters "
                 "and two low ones over roughly a day.",
        "sourdough": "A flour and water mixture left alone gathers wild yeasts "
                     "and bacteria from the air and the grain until it bubbles "
                     "reliably, after which a spoonful of it will raise a loaf "
                     "given warmth, salt, and enough time to ferment.",
        "cricket": "A bowler runs up and releases toward a batter defending "
                   "three wooden stumps, and runs accumulate either by the two "
                   "batters exchanging ends or by the ball reaching or clearing "
                   "the boundary rope without being caught first.",
        "cartography": "Any attempt to draw a curved surface onto a flat sheet "
                       "distorts something, so a projection is chosen for what "
                       "it preserves: angle, area, or distance along particular "
                       "lines, never all three together at once.",
        "espresso": "Hot water forced through finely ground coffee under "
                    "pressure produces a small concentrated drink topped with "
                    "foam, and the grind, dose, and pour duration are the three "
                    "levers a barista adjusts to fix a sour or bitter result.",
        "sailing": "A boat can travel against the wind by tacking, angling "
                   "across it and zigzagging upwind, because the sail acts as a "
                   "wing generating lift sideways rather than simply catching "
                   "and being pushed by moving air.",
    }

    def write_body(self, slug, prose, entry_type="semantic"):
        path = self.entry_path(entry_type, slug)
        head, _, _ = path.read_text().partition("---\n")[2].partition("\n---\n")
        path.write_text(f"---\n{head}\n---\n\n{prose}\n")

    def setUp(self):
        super().setUp()
        bodies = {"stated-plainly": self.CLAIM, "stated-again": self.RESTATEMENT}
        bodies.update(self.FILLER)
        for slug, prose in bodies.items():
            self.run_kb("new", slug, "--type", "semantic")
            self.write_body(slug, prose)

    def candidates(self, *args):
        result = self.run_kb("candidates", "--json", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def pair_names(self, report):
        return {frozenset((p["a"], p["b"])) for p in report["pairs"]}

    THE_PAIR = frozenset(("stated-plainly", "stated-again"))

    def test_the_paraphrase_dupes_must_miss_is_the_one_candidates_must_catch(self):
        self.assertIn(self.THE_PAIR, self.pair_names(self.candidates("-n", "1")))
        dupes = json.loads(self.run_kb("dupes", "--json").stdout)
        self.assertNotIn(self.THE_PAIR,
                         {frozenset((p["a"], p["b"])) for p in dupes["pairs"]})

    def test_it_narrows_rather_than_listing_every_pair(self):
        report = self.candidates("-n", "1")
        entries = len(self.FILLER) + 2
        self.assertLess(len(report["pairs"]), entries * (entries - 1) // 2)

    def test_more_neighbours_never_loses_a_candidate(self):
        narrow = self.pair_names(self.candidates("-n", "1"))
        wide = self.pair_names(self.candidates("-n", "3"))
        self.assertTrue(narrow <= wide)

    def test_output_refuses_to_call_them_duplicates(self):
        out = self.run_kb("candidates").stdout
        self.assertIn("candidates, not duplicates", out)

    def test_a_judged_pair_leaves_the_queue(self):
        self.run_kb("judge", "stated-plainly", "stated-again", "distinct",
                    "--agreement", "agree")
        self.assertNotIn(self.THE_PAIR, self.pair_names(self.candidates("-n", "1")))

    def test_a_judged_pair_is_still_visible_with_all(self):
        self.run_kb("judge", "stated-plainly", "stated-again", "distinct",
                    "--agreement", "agree")
        self.assertIn(self.THE_PAIR, self.pair_names(self.candidates("-n", "1", "--all")))

    def test_a_confirmed_duplicate_stays_until_it_is_merged(self):
        self.run_kb("judge", "stated-plainly", "stated-again", "duplicate")
        pairs = self.candidates("-n", "1")["pairs"]
        pair = next(p for p in pairs if {p["a"], p["b"]} == set(self.THE_PAIR))
        self.assertEqual(pair["verdict"], "duplicate")
        self.assertFalse(pair["verdict_stale"])

    def test_rewriting_an_entry_reopens_the_question(self):
        self.run_kb("judge", "stated-plainly", "stated-again", "distinct",
                    "--agreement", "agree")
        self.write_body("stated-again", self.RESTATEMENT + " Also, one more thing.")
        pairs = self.candidates("-n", "1")["pairs"]
        pair = next(p for p in pairs if {p["a"], p["b"]} == set(self.THE_PAIR))
        self.assertTrue(pair["verdict_stale"])
        self.assertIn("TEXT CHANGED SINCE", self.run_kb("candidates", "-n", "1").stdout)

    def test_re_verifying_an_entry_does_not_reopen_it(self):
        """A verdict is about what an entry claims, not about its metadata."""
        self.run_kb("judge", "stated-plainly", "stated-again", "distinct",
                    "--agreement", "agree")
        self.run_kb("verify", "stated-again", "--confidence", "verified")
        self.run_kb("link", "stated-again", "tides")
        self.assertNotIn(self.THE_PAIR, self.pair_names(self.candidates("-n", "1")))

    def test_the_verdict_does_not_care_which_order_the_pair_was_given_in(self):
        self.run_kb("judge", "stated-again", "stated-plainly", "distinct",
                    "--agreement", "agree")
        self.assertNotIn(self.THE_PAIR, self.pair_names(self.candidates("-n", "1")))

    def test_archived_entries_are_out_of_the_candidate_set(self):
        self.run_kb("archive", "stated-again")
        self.assertNotIn(self.THE_PAIR, self.pair_names(self.candidates("-n", "3")))

    def test_short_entries_are_reported_rather_than_silently_skipped(self):
        self.run_kb("new", "stub-entry", "--type", "semantic")
        self.write_body("stub-entry", "Too short to judge.")
        self.assertIn("stub-entry", self.candidates()["too_short"])

    def test_an_entry_cannot_duplicate_itself(self):
        result = self.run_kb("judge", "stated-plainly", "stated-plainly", "distinct")
        self.assertNotEqual(result.returncode, 0)

    def test_judging_an_unknown_entry_fails_loudly(self):
        result = self.run_kb("judge", "stated-plainly", "no-such-entry", "distinct")
        self.assertNotEqual(result.returncode, 0)

    def test_dupes_points_at_candidates_for_the_case_it_cannot_cover(self):
        self.assertIn("kb.py candidates", self.run_kb("dupes").stdout)


class TestContradictions(TestCandidates):
    """The second axis: do these two entries disagree?

    Measured before it was built: contradicting pairs sit anywhere from #2 to
    #107 of 435 by topical similarity, claim-level alignment finds 4 of 9, and
    negation polarity finds 5 of 9 while missing every pair that disagrees by
    competing positive assertion. So there is no detector — the blocker built
    for duplicates already surfaces the pairs, and this axis is where an agent
    that read them writes the answer down.
    """

    def ledger(self):
        return json.loads((self.root / ".kb" / "verdicts.json").read_text())["verdicts"]

    def judge(self, *args):
        result = self.run_kb("judge", "stated-plainly", "stated-again", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def in_queue(self):
        return self.THE_PAIR in self.pair_names(self.candidates("-n", "1"))

    def statuses(self):
        report = json.loads(self.run_kb("status", "--json").stdout)
        return {r["name"]: r["status"] for r in report}

    def test_half_judging_a_pair_does_not_settle_it(self):
        """Silence on the second question must not read as 'checked, fine'."""
        out = self.judge("distinct").stdout
        self.assertIn("half-judged", out)
        self.assertTrue(self.in_queue())
        self.assertIn("never checked for contradiction",
                      self.run_kb("candidates", "-n", "1").stdout)

    def test_an_unexamined_pair_stores_no_agreement_at_all(self):
        """Absent, not a default value — an old ledger must read as unexamined."""
        self.judge("distinct")
        self.assertNotIn("agreement", self.ledger()[0])

    def test_answering_both_questions_settles_the_pair(self):
        self.judge("distinct", "--agreement", "agree")
        self.assertFalse(self.in_queue())
        self.assertEqual(self.ledger()[0]["agreement"], "agree")

    def test_a_contradiction_stays_in_the_queue_until_it_is_reconciled(self):
        self.judge("overlap", "--agreement", "contradict")
        self.assertTrue(self.in_queue())
        self.assertIn("CONTRADICTION standing",
                      self.run_kb("candidates", "-n", "1").stdout)

    def test_a_contradiction_is_reported_against_both_entries(self):
        """Neither entry is identifiable as the wrong one without reading them."""
        self.judge("overlap", "--agreement", "contradict")
        report = json.loads(self.run_kb("triage", "--json").stdout)
        flagged = {r["name"]: [x["code"] for x in r["reasons"]] for r in report}
        self.assertIn("contradiction", flagged.get("stated-plainly", []))
        self.assertIn("contradiction", flagged.get("stated-again", []))

    def test_contradiction_outranks_every_other_status(self):
        stamp = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
        self.edit_frontmatter("semantic", "stated-again", last_verified=stamp)
        self.assertEqual(self.statuses()["stated-again"], "stale")
        self.judge("overlap", "--agreement", "contradict")
        self.assertEqual(self.statuses()["stated-again"], "contradicted")

    def test_it_is_a_triage_reason_not_a_lint_failure(self):
        """Lint checks form. Whether two entries can both be true is not form."""
        self.judge("overlap", "--agreement", "contradict")
        self.assertEqual(self.run_kb("lint").returncode, 0)
        flagged = self.run_kb("triage", "--reason", "contradiction").stdout
        self.assertIn("stated-plainly", flagged)
        self.assertIn("stated-again", flagged)

    def test_rewriting_an_entry_clears_the_standing_contradiction(self):
        """Resolving one by editing is self-clearing; the pair comes back to judge."""
        self.judge("overlap", "--agreement", "contradict")
        self.write_body("stated-again", self.RESTATEMENT + " On reflection, no.")
        self.assertNotIn("contradicted", self.statuses().values())
        pair = next(p for p in self.candidates("-n", "1")["pairs"]
                    if {p["a"], p["b"]} == set(self.THE_PAIR))
        self.assertTrue(pair["verdict_stale"])

    def test_re_verifying_does_not_clear_a_contradiction(self):
        """Metadata is not the claim, so stamping a date settles nothing."""
        self.judge("overlap", "--agreement", "contradict")
        self.run_kb("verify", "stated-again", "--confidence", "verified")
        self.assertEqual(self.statuses()["stated-again"], "contradicted")

    def test_archiving_one_side_ends_the_disagreement(self):
        """A retired entry no longer speaks, so it can no longer disagree."""
        self.judge("overlap", "--agreement", "contradict")
        self.run_kb("archive", "stated-again")
        self.assertNotIn("contradicted", self.statuses().values())

    def test_the_two_axes_are_recorded_independently(self):
        self.judge("distinct", "--agreement", "contradict")
        entry = self.ledger()[0]
        self.assertEqual((entry["verdict"], entry["agreement"]),
                         ("distinct", "contradict"))

    def test_an_unknown_agreement_is_rejected(self):
        result = self.run_kb("judge", "stated-plainly", "stated-again",
                             "distinct", "--agreement", "probably")
        self.assertNotEqual(result.returncode, 0)

    def test_the_prompt_asks_for_both_answers(self):
        out = self.run_kb("candidates", "-n", "1").stdout
        self.assertIn("--agreement", out)
        self.assertIn("Two questions per pair", out)

    def test_re_judging_keeps_the_reasoning_from_the_first_pass(self):
        """Adding this axis re-opened every already-judged pair; a second
        judgement must not silently spend the first one's note."""
        self.judge("overlap", "--note", "two halves of one topic")
        self.judge("overlap", "--agreement", "agree")
        self.assertEqual(self.ledger()[0]["note"], "two halves of one topic")

    def test_a_note_can_still_be_replaced_or_cleared_on_purpose(self):
        self.judge("overlap", "--note", "first thought")
        self.judge("overlap", "--agreement", "agree", "--note", "second thought")
        self.assertEqual(self.ledger()[0]["note"], "second thought")
        self.judge("overlap", "--agreement", "agree", "--note", "")
        self.assertEqual(self.ledger()[0]["note"], "")

    def test_the_legend_explains_how_to_leave_the_contradicted_state(self):
        out = self.run_kb("status", "--legend").stdout
        self.assertIn("Contradicted", out)
        self.assertIn("--agreement agree", out)


class TestConsolidate(TestCandidates):
    """What a judged pair still owes.

    `judge` says what two entries are to each other and then the pair settles
    out of `candidates` forever, so the one-line advice it prints — link them
    if they are not linked — is given once and never checked again. These
    tests pin the three queues that check it, and the measurement behind the
    third: passage-level shingle containment found 1 of 7 planted restatements
    where scoring the passage as a BM25 query found 7 of 7.
    """

    # A paragraph restating the `cartography` filler in different words, to be
    # dropped into an entry that has nothing to do with it. This is the shape
    # an agent produces when it re-records something the store already holds.
    # Deliberately not about the store itself: `stated-plainly` and
    # `stated-again` already restate each other, so a passage on that subject
    # would have two equally right answers and test nothing.
    RESTATING_PASSAGE = (
        "A note on why no single map can be trusted for everything at once: "
        "flattening a sphere onto paper always deforms it, so whoever draws "
        "one picks what survives — the shapes of angles, the relative sizes "
        "of regions, or true spacing along a few chosen lines — and accepts "
        "that whatever was not picked comes out wrong."
    )

    def consolidate(self, *args):
        result = self.run_kb("consolidate", "--json", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def judge_the_pair(self, verdict, *extra):
        self.run_kb("judge", "stated-plainly", "stated-again", verdict,
                    "--agreement", "agree", *extra)

    def edge_names(self, report):
        return {frozenset((p["a"], p["b"])) for p in report["missing_edges"]}

    def append_to(self, slug, text, entry_type="semantic"):
        path = self.entry_path(entry_type, slug)
        path.write_text(path.read_text().rstrip("\n") + "\n\n" + text + "\n")

    # --- the merge queue, which this store has never populated -------------

    def test_a_duplicate_verdict_becomes_a_merge_proposal(self):
        self.judge_the_pair("duplicate")
        report = self.consolidate()
        self.assertEqual(len(report["merges"]), 1)
        self.assertEqual(frozenset(("stated-plainly", "stated-again")),
                         frozenset((report["merges"][0]["a"],
                                    report["merges"][0]["b"])))

    def test_nothing_judged_means_nothing_proposed(self):
        report = self.consolidate()
        self.assertEqual(report["merges"], [])
        self.assertEqual(report["missing_edges"], [])

    def test_an_empty_merge_queue_says_so_rather_than_printing_nothing(self):
        self.assertIn("none", self.run_kb("consolidate").stdout)

    # --- the missing-edge queue, which is where the defects actually were --

    def test_an_overlap_with_no_edge_between_them_is_proposed(self):
        self.judge_the_pair("overlap")
        self.assertIn(self.THE_PAIR, self.edge_names(self.consolidate()))

    def test_linking_the_pair_clears_the_proposal(self):
        self.judge_the_pair("overlap")
        self.run_kb("link", "stated-plainly", "stated-again")
        self.assertNotIn(self.THE_PAIR, self.edge_names(self.consolidate()))

    def test_one_direction_of_link_is_enough(self):
        self.judge_the_pair("overlap")
        self.run_kb("link", "stated-again", "stated-plainly")
        self.assertNotIn(self.THE_PAIR, self.edge_names(self.consolidate()))

    def test_a_distinct_verdict_owes_no_edge(self):
        self.judge_the_pair("distinct")
        self.assertNotIn(self.THE_PAIR, self.edge_names(self.consolidate()))

    def test_lint_cannot_see_the_missing_edge_that_consolidate_reports(self):
        # Both entries are linked to something, so neither is an orphan and no
        # link dangles. This is the whole reason the queue exists: a missing
        # edge is a property of a pair, and lint only sees single entries.
        self.judge_the_pair("overlap")
        self.run_kb("link", "stated-plainly", "tides")
        self.run_kb("link", "stated-again", "sourdough")
        self.assertEqual(self.run_kb("lint").returncode, 0)
        self.assertIn(self.THE_PAIR, self.edge_names(self.consolidate()))

    # --- a verdict only speaks for the text it was passed on ---------------

    def test_rewriting_an_entry_withdraws_its_proposals(self):
        self.judge_the_pair("overlap")
        self.assertIn(self.THE_PAIR, self.edge_names(self.consolidate()))
        self.write_body("stated-plainly", self.FILLER["cricket"])
        self.assertNotIn(self.THE_PAIR, self.edge_names(self.consolidate()))

    def test_archiving_an_entry_withdraws_its_proposals(self):
        self.judge_the_pair("overlap")
        self.run_kb("archive", "stated-again")
        self.assertNotIn(self.THE_PAIR, self.edge_names(self.consolidate()))

    def test_re_verifying_does_not_withdraw_a_proposal(self):
        # Verification changes provenance, not the claim — it must not expire
        # a judgement about the claim, and so must not expire what that
        # judgement owes either.
        self.judge_the_pair("overlap")
        self.run_kb("verify", "stated-plainly")
        self.assertIn(self.THE_PAIR, self.edge_names(self.consolidate()))

    # --- restated passages, and the metric that does not find them ---------

    def restatement_targets(self, report, host):
        return {p["target"] for p in report["restatements"] if p["host"] == host}

    def test_a_restating_passage_points_at_the_entry_it_restates(self):
        self.append_to("espresso", self.RESTATING_PASSAGE)
        self.assertIn("cartography", self.restatement_targets(
            self.consolidate(), "espresso"))

    def test_containment_cannot_find_what_this_finds(self):
        # The inverse of TestDupes.test_a_paraphrase_is_not_flagged, one level
        # down: the passage `dupes` must stay silent about is the passage
        # `consolidate` must surface. Shingles measure shared phrasing, which
        # is exactly what a restatement does not share.
        self.append_to("espresso", self.RESTATING_PASSAGE)
        dupes = json.loads(self.run_kb("dupes", "--json").stdout)
        self.assertNotIn(frozenset(("espresso", "cartography")),
                         {frozenset((p["a"], p["b"])) for p in dupes["pairs"]})
        self.assertIn("cartography", self.restatement_targets(
            self.consolidate(), "espresso"))

    def test_a_passage_at_home_in_its_own_entry_is_not_proposed(self):
        # The same paragraph, in the entry it restates. It is now where it
        # belongs, and nothing should be proposed about it — which only works
        # because the host is scored with the passage removed.
        self.append_to("cartography", self.RESTATING_PASSAGE)
        self.assertEqual(set(), self.restatement_targets(
            self.consolidate(), "cartography"))

    def test_it_reads_a_fraction_of_the_passage_space(self):
        self.append_to("espresso", self.RESTATING_PASSAGE)
        report = self.consolidate()
        entries = len(self.FILLER) + 2
        self.assertLess(len(report["restatements"]), entries * (entries - 1))

    def test_a_wider_margin_never_adds_a_proposal(self):
        self.append_to("espresso", self.RESTATING_PASSAGE)
        def keys(m):
            return {(p["host"], p["target"])
                    for p in self.consolidate("--margin", m)["restatements"]}
        self.assertTrue(keys("3.0") <= keys("1.5") <= keys("1.0"))

    def test_a_proposal_carries_what_is_needed_to_rule_on_it(self):
        self.append_to("espresso", self.RESTATING_PASSAGE)
        self.run_kb("judge", "espresso", "cartography", "overlap",
                    "--agreement", "agree")
        p = next(p for p in self.consolidate()["restatements"]
                 if (p["host"], p["target"]) == ("espresso", "cartography"))
        self.assertFalse(p["linked"])
        self.assertEqual(p["verdict"], "overlap")
        self.assertIn("no single map", p["passage"])

    # --- it proposes, it never rewrites ------------------------------------

    def test_it_only_proposes(self):
        self.judge_the_pair("overlap")
        self.append_to("espresso", self.RESTATING_PASSAGE)
        before = {p: p.read_text() for p in
                  (self.root / "memory").rglob("*.md")}
        self.run_kb("consolidate")
        self.assertEqual(before, {p: p.read_text() for p in
                                  (self.root / "memory").rglob("*.md")})

    def test_it_prints_the_command_that_applies_each_proposal(self):
        self.judge_the_pair("overlap")
        out = self.run_kb("consolidate").stdout
        self.assertIn("kb.py link stated-again stated-plainly", out)

    def test_one_queue_can_be_asked_for_alone(self):
        self.judge_the_pair("duplicate")
        out = self.run_kb("consolidate", "--only", "merges").stdout
        self.assertIn("MERGE", out)
        self.assertNotIn("RESTATED", out)


class TestConfidenceDecay(KbTestCase):
    """Age demotes confidence at read time; the file on disk is never rewritten."""

    def setUp(self):
        super().setUp()
        self.run_kb("new", "aged-fact", "--type", "semantic")
        self.run_kb("set", "aged-fact", "confidence", "verified")

    def age(self, days, slug="aged-fact"):
        stamp = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        self.edit_frontmatter("semantic", slug, last_verified=stamp, created=stamp)

    def status_row(self, slug="aged-fact"):
        report = json.loads(self.run_kb("status", "--json").stdout)
        return next(r for r in report if r["name"] == slug)

    def test_a_fresh_entry_is_not_demoted(self):
        row = self.status_row()
        self.assertEqual(row["effective_confidence"], "verified")
        self.assertEqual(row["decayed_by"], 0)

    def test_one_staleness_period_drops_one_level(self):
        self.age(95)
        row = self.status_row()
        self.assertEqual(row["effective_confidence"], "high")
        self.assertEqual(row["decayed_by"], 1)

    def test_two_staleness_periods_drop_two_levels(self):
        self.age(200)
        row = self.status_row()
        self.assertEqual(row["effective_confidence"], "medium")
        self.assertEqual(row["decayed_by"], 2)

    def test_decay_bottoms_out_rather_than_running_off_the_scale(self):
        self.age(5000)
        row = self.status_row()
        self.assertEqual(row["effective_confidence"], "unverified")
        self.assertEqual(row["decayed_by"], 4)

    def test_the_stored_confidence_is_never_rewritten(self):
        self.age(365)
        self.run_kb("status")
        self.run_kb("search", "aged")
        self.assertIn("confidence: verified", self.entry_path("semantic", "aged-fact").read_text())
        self.assertEqual(self.status_row()["confidence"], "verified")

    def test_verifying_undoes_the_decay(self):
        self.age(365)
        self.run_kb("verify", "aged-fact")
        row = self.status_row()
        self.assertEqual(row["effective_confidence"], "verified")
        self.assertEqual(row["decayed_by"], 0)

    def test_an_aged_entry_ranks_below_an_equal_fresh_one(self):
        self.run_kb("new", "fresh-fact", "--type", "semantic")
        self.run_kb("set", "fresh-fact", "confidence", "verified")
        for slug in ("aged-fact", "fresh-fact"):
            self.run_kb("set", slug, "description", "identical wording for ranking")
        self.age(400)
        hits = json.loads(self.run_kb("search", "identical wording", "--json").stdout)
        names = [h["name"] for h in hits]
        self.assertLess(names.index("fresh-fact"), names.index("aged-fact"))

    def test_the_context_pack_reports_both_numbers(self):
        self.age(365)
        self.run_kb("set", "aged-fact", "description", "a claim about ageing")
        out = self.run_kb("context", "ageing claim").stdout
        self.assertIn("recorded as verified, aged", out)

    def test_search_flags_a_decayed_hit(self):
        self.age(365)
        self.run_kb("set", "aged-fact", "description", "a claim about ageing")
        out = self.run_kb("search", "ageing claim").stdout
        self.assertIn("verified -> unverified, aged", out)


class TestEval(KbTestCase):
    """`kb.py eval` against a planted store, so the numbers are known exactly.

    The real store's scores are asserted in tests/test_retrieval_golden.py;
    this only checks the command's own behaviour.
    """

    def setUp(self):
        super().setUp()
        for slug, description in (
            ("tides-of-mars", "why the red planet has no ocean swell"),
            ("bread-proofing", "dough left to rise in a warm kitchen"),
        ):
            self.run_kb("new", slug, "--type", "semantic")
            self.run_kb("set", slug, "description", description)

    def write_golden(self, queries):
        path = self.root / ".kb" / "golden.json"
        path.write_text(json.dumps({"version": 1, "queries": queries}))

    def test_no_golden_file_is_reported_rather_than_scored(self):
        result = self.run_kb("eval")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no golden queries", result.stdout)

    def test_a_query_that_lands_first_scores_a_clean_sweep(self):
        self.write_golden([{"query": "ocean swell red planet",
                            "expect": "tides-of-mars"}])
        report = json.loads(self.run_kb("eval", "--json").stdout)
        self.assertEqual(report["summary"]["success_at_1"], 1.0)
        self.assertEqual(report["summary"]["mrr"], 1.0)
        self.assertEqual(report["queries"][0]["rank"], 1)

    def test_an_also_ok_entry_counts_for_recall_but_not_for_success_at_1(self):
        self.write_golden([{"query": "dough rise warm kitchen",
                            "expect": "tides-of-mars",
                            "also_ok": ["bread-proofing"]}])
        summary = json.loads(self.run_kb("eval", "--json").stdout)["summary"]
        self.assertEqual(summary["success_at_1"], 0.0)
        self.assertEqual(summary["recall_at_3"], 1.0)

    def test_an_entry_that_never_appears_scores_zero_not_a_crash(self):
        self.write_golden([{"query": "quenelle sabayon consommé",
                            "expect": "bread-proofing"}])
        report = json.loads(self.run_kb("eval", "--json").stdout)
        self.assertIsNone(report["queries"][0]["rank"])
        self.assertEqual(report["summary"]["mrr"], 0.0)

    def test_an_expectation_naming_a_missing_entry_fails_the_command(self):
        self.write_golden([{"query": "ocean swell", "expect": "no-such-entry"}])
        result = self.run_kb("eval")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no longer exist", result.stderr)
        self.assertIn("no-such-entry", result.stderr)

    def test_malformed_query_rows_are_skipped_not_fatal(self):
        self.write_golden([
            {"query": "ocean swell red planet", "expect": "tides-of-mars"},
            {"query": "missing an expectation"},
            {"expect": "missing a query"},
            "not even a dict",
        ])
        summary = json.loads(self.run_kb("eval", "--json").stdout)["summary"]
        self.assertEqual(summary["queries"], 1)

    def test_unreadable_golden_file_is_an_error(self):
        (self.root / ".kb" / "golden.json").write_text("{not json")
        result = self.run_kb("eval")
        self.assertEqual(result.returncode, 2)
        self.assertIn("could not load", result.stderr)

    def test_only_wrong_answers_are_listed_unless_all_is_asked_for(self):
        self.write_golden([{"query": "ocean swell red planet",
                            "expect": "tides-of-mars"}])
        self.assertNotIn("ocean swell", self.run_kb("eval").stdout)
        self.assertIn("ocean swell", self.run_kb("eval", "--all").stdout)


class TestStats(KbTestCase):
    def test_an_empty_store_says_so(self):
        self.assertIn("empty store", self.run_kb("stats").stdout)

    def test_counts_split_by_type_and_confidence(self):
        self.run_kb("new", "one-fact", "--type", "semantic")
        self.run_kb("new", "a-run", "--type", "episodic")
        self.run_kb("set", "one-fact", "confidence", "verified")
        stats = json.loads(self.run_kb("stats", "--json").stdout)
        self.assertEqual(stats["entries"], 2)
        self.assertEqual(stats["by_type"], {"semantic": 1, "episodic": 1})
        self.assertEqual(stats["by_confidence"]["verified"], 1)

    def test_the_graph_numbers_count_both_directions(self):
        self.run_kb("new", "hub", "--type", "semantic")
        self.run_kb("new", "spoke", "--type", "semantic")
        self.run_kb("link", "hub", "spoke")
        stats = json.loads(self.run_kb("stats", "--json").stdout)
        self.assertEqual(stats["links"]["edges"], 1)
        self.assertEqual(stats["links"]["per_entry"], 0.5)
        # hub points at spoke and nothing points back at hub.
        self.assertEqual(stats["links"]["orphans"], 1)
        self.assertEqual(stats["links"]["unlinked"], 1)

    def test_an_archived_entry_is_counted_apart_from_the_live_ones(self):
        self.run_kb("new", "retired", "--type", "semantic")
        self.run_kb("archive", "retired")
        stats = json.loads(self.run_kb("stats", "--json").stdout)
        self.assertEqual(stats["entries"], 1)
        self.assertEqual(stats["archived"], 1)
        self.assertIn("1 archived", self.run_kb("stats").stdout)

    def test_decay_is_reported_against_what_was_written(self):
        self.run_kb("new", "aged", "--type", "semantic")
        self.run_kb("set", "aged", "confidence", "verified")
        old = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
        self.edit_frontmatter("semantic", "aged", last_verified=old)
        stats = json.loads(self.run_kb("stats", "--json").stdout)
        self.assertEqual(stats["by_confidence"], {"verified": 1})
        self.assertEqual(stats["by_effective_confidence"], {"unverified": 1})
        self.assertEqual(stats["decayed"], 1)

    def test_growth_is_grouped_by_month(self):
        self.run_kb("new", "recent", "--type", "semantic")
        month = datetime.date.today().isoformat()[:7]
        stats = json.loads(self.run_kb("stats", "--json").stdout)
        self.assertEqual(stats["created_by_month"], [[month, 1]])
        self.assertIn(month, self.run_kb("stats").stdout)


if __name__ == "__main__":
    unittest.main()
