#!/usr/bin/env python3
"""Stdlib unittest suite for scripts/kb.py, run against a throwaway temp KB.

Each test copies kb.py plus the real template/schema into a fresh temp
directory (so kb.py's module-level ROOT/MEMORY resolve there, not into the
real repo) and drives it as a subprocess, the same way a user would.
"""
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
        (self.root / "memory" / "templates").mkdir(parents=True)
        (self.root / "memory" / "schema").mkdir(parents=True)
        shutil.copy(REPO_ROOT / "scripts" / "kb.py", self.root / "scripts" / "kb.py")
        shutil.copy(
            REPO_ROOT / "memory" / "templates" / "entry.template.md",
            self.root / "memory" / "templates" / "entry.template.md",
        )
        shutil.copy(
            REPO_ROOT / "memory" / "schema" / "entry.schema.json",
            self.root / "memory" / "schema" / "entry.schema.json",
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


if __name__ == "__main__":
    unittest.main()
