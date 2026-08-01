#!/usr/bin/env python3
"""Tests for scripts/kb_due_issue.py — rendering kb.py due --json as an issue body.

Pure formatting with no filesystem/network coupling, so this imports the
module directly rather than driving it as a subprocess (unlike the other
suites, which need a throwaway KB for kb.py's module-level ROOT to resolve
into).
"""
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import kb_due_issue  # noqa: E402


class TestRender(unittest.TestCase):
    def test_no_rows_still_has_a_title_and_empty_body_list(self):
        title, body = kb_due_issue.render([])
        self.assertEqual(title, kb_due_issue.ISSUE_TITLE)
        self.assertNotIn("- [ ]", body)

    def test_overdue_and_upcoming_are_both_listed(self):
        rows = [
            {"name": "past-task", "due": "2000-01-01", "days": -1000,
             "overdue": True, "description": "old thing"},
            {"name": "soon-task", "due": "2099-01-01", "days": 5,
             "overdue": False, "description": "new thing"},
        ]
        title, body = kb_due_issue.render(rows)
        self.assertEqual(title, "Knowledge base: entries coming due")
        self.assertIn("- [ ] `past-task` — due 2000-01-01 (**OVERDUE**) — old thing", body)
        self.assertIn("- [ ] `soon-task` — due 2099-01-01 (in 5d) — new thing", body)

    def test_body_tells_the_reader_not_to_hand_edit_it(self):
        _, body = kb_due_issue.render([])
        self.assertIn("overwritten on the next run", body)


class TestMain(unittest.TestCase):
    def run_script(self, payload):
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "kb_due_issue.py")],
            input=json.dumps(payload), capture_output=True, text=True,
        )

    def test_reads_json_from_stdin_and_prints_title_body_count(self):
        rows = [{"name": "x", "due": "2030-01-01", "days": 1, "overdue": False,
                 "description": "d"}]
        result = self.run_script(rows)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out["title"], kb_due_issue.ISSUE_TITLE)
        self.assertEqual(out["count"], 1)
        self.assertIn("x", out["body"])

    def test_empty_list_reports_zero_count(self):
        result = self.run_script([])
        out = json.loads(result.stdout)
        self.assertEqual(out["count"], 0)


if __name__ == "__main__":
    unittest.main()
