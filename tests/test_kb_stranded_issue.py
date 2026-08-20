#!/usr/bin/env python3
"""Tests for scripts/kb_stranded_issue.py — the stranded-branch detector.

Pure formatting with no git/network coupling, so this imports the module
directly, same as test_kb_due_issue.py. The enumeration half lives in
.github/workflows/kb-stranded.yml, which nothing here can stand up.

The cases that matter are the ones that keep the detector from becoming
noise: a branch a session is still working on must not fire, a squash-merged
leftover must not fire, and the acknowledged list must not be growable
without a documented reason.
"""
import json
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import kb_stranded_issue as ksi  # noqa: E402

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


def row(branch, ahead=1, hours_old=48, pr=None):
    tip = (NOW - timedelta(hours=hours_old)).isoformat().replace("+00:00", "Z")
    return {"branch": branch, "ahead": ahead, "tip": tip, "pr": pr}


class TestClassify(unittest.TestCase):
    def test_a_stale_claude_branch_with_commits_is_actionable(self):
        actionable, acked = ksi.classify([row("claude/foo-abc123")], NOW)
        self.assertEqual([r["branch"] for r in actionable], ["claude/foo-abc123"])
        self.assertEqual(acked, [])

    def test_a_branch_a_session_may_still_be_working_on_does_not_fire(self):
        # The whole margin of the 12h threshold: every legitimately-merged PR
        # in this repo merged within 62 minutes, so a fresh branch is a
        # session in flight, not a stranding.
        actionable, _ = ksi.classify([row("claude/fresh", hours_old=2)], NOW)
        self.assertEqual(actionable, [])

    def test_the_threshold_is_inclusive_at_its_boundary(self):
        at, _ = ksi.classify([row("claude/edge", hours_old=ksi.STALE_HOURS)], NOW)
        under, _ = ksi.classify([row("claude/edge", hours_old=ksi.STALE_HOURS - 0.1)], NOW)
        self.assertEqual(len(at), 1)
        self.assertEqual(under, [])

    def test_a_squash_merged_leftover_is_not_stranded(self):
        # `ahead == 0` — every line of it is already on main (0sq8ef, 4c7ia8).
        # Ancestry, not `git diff`, is what distinguishes these.
        actionable, acked = ksi.classify([row("claude/merged", ahead=0)], NOW)
        self.assertEqual(actionable, [])
        self.assertEqual(acked, [])

    def test_a_human_branch_is_never_stranded_work(self):
        actionable, _ = ksi.classify([row("feature/jerry-thing"), row("main")], NOW)
        self.assertEqual(actionable, [])

    def test_acknowledged_branches_are_reported_but_never_counted(self):
        branch = sorted(ksi.ACKNOWLEDGED)[0]
        actionable, acked = ksi.classify([row(branch, hours_old=400)], NOW)
        self.assertEqual(actionable, [])
        self.assertEqual([r["branch"] for r in acked], [branch])
        self.assertTrue(acked[0]["reason"])

    def test_longest_stranded_sorts_first(self):
        rows = [row("claude/newer", hours_old=20), row("claude/older", hours_old=300)]
        actionable, _ = ksi.classify(rows, NOW)
        self.assertEqual([r["branch"] for r in actionable], ["claude/older", "claude/newer"])

    def test_a_tip_in_the_future_does_not_go_negative(self):
        actionable, _ = ksi.classify([row("claude/skewed", hours_old=-5)], NOW)
        self.assertEqual(actionable, [])

    def test_a_naive_timestamp_is_read_as_utc(self):
        rows = [{"branch": "claude/naive", "ahead": 1, "tip": "2026-08-01T00:00:00"}]
        actionable, _ = ksi.classify(rows, NOW)
        self.assertEqual(len(actionable), 1)


class TestRender(unittest.TestCase):
    def test_count_drives_the_workflows_close_branch(self):
        # Only acknowledged branches left => count 0 => the workflow closes the
        # issue. This is the case ROADMAP.md refused to ship without: a cron
        # that opens an issue no routine session can ever close.
        rows = [row(b, hours_old=400) for b in ksi.ACKNOWLEDGED]
        _, body, count = ksi.render(rows, NOW)
        self.assertEqual(count, 0)
        self.assertIn("Acknowledged", body)
        self.assertNotIn("- [ ]", body)

    def test_an_open_unmerged_pr_is_named_in_the_row(self):
        # The 2026-08-10 stranding had PR #55 open for four days; "no PR" and
        # "PR open but unmerged" need different actions from the reader.
        _, body, count = ksi.render([row("claude/x", ahead=1, pr=55)], NOW)
        self.assertEqual(count, 1)
        self.assertIn("PR #55 open, unmerged", body)

    def test_a_branch_with_no_pr_says_so(self):
        _, body, _ = ksi.render([row("claude/x")], NOW)
        self.assertIn("no PR", body)

    def test_commit_count_and_age_are_both_shown(self):
        _, body, _ = ksi.render([row("claude/x", ahead=2, hours_old=72)], NOW)
        self.assertIn("2 commits off `main`", body)
        self.assertIn("3.0d", body)
        _, single, _ = ksi.render([row("claude/y", ahead=1, hours_old=13)], NOW)
        self.assertIn("1 commit off `main`", single)
        self.assertIn("13h", single)

    def test_body_states_the_remedy_and_the_gate(self):
        # A detector that reports without saying what to do reproduces the
        # contradiction that caused three of the six strandings.
        _, body, _ = ksi.render([row("claude/x")], NOW)
        self.assertIn("Land each one", body)
        self.assertIn("*start*", body)

    def test_body_tells_the_reader_not_to_hand_edit_it(self):
        _, body, _ = ksi.render([], NOW)
        self.assertIn("overwritten on the next run", body)

    def test_title_is_stable_because_the_workflow_finds_the_issue_by_it(self):
        title, _, _ = ksi.render([], NOW)
        self.assertEqual(title, ksi.ISSUE_TITLE)
        self.assertIn(ksi.ISSUE_TITLE, (REPO_ROOT / ".github/workflows/kb-stranded.yml").read_text())


class TestTheAcknowledgedListCannotGrowQuietly(unittest.TestCase):
    """The acknowledged list is the one way to silence this detector.

    ROADMAP.md declined to build the detector partly because its standing
    fires are two branches only Jerry can delete. Allowing them is necessary;
    allowing *anything else* through the same door would turn a real stranding
    into a config change, so both guards below are load-bearing.
    """

    def test_every_acknowledged_branch_carries_a_reason(self):
        for branch, reason in ksi.ACKNOWLEDGED.items():
            self.assertTrue(reason.strip(), f"{branch} has no reason")
            self.assertIn("delete", reason.lower(), f"{branch}'s reason must say who clears it")

    def test_every_acknowledged_branch_is_documented_in_autonomy_md(self):
        charter = (REPO_ROOT / "AUTONOMY.md").read_text()
        for branch in ksi.ACKNOWLEDGED:
            self.assertIn(branch, charter, f"{branch} is silenced here but undocumented")

    def test_the_delete_command_names_every_acknowledged_branch(self):
        for branch in ksi.ACKNOWLEDGED:
            self.assertIn(branch, ksi.DELETE_COMMAND)


class TestTheScheduleReachesTheSessionItWarns(unittest.TestCase):
    """The issue is useless if it arrives after the session that would act.

    `AUTONOMY.md` tells a session that an open tracking issue is the first
    thing to clear. That instruction is only reachable if the issue exists
    when the session looks. It did not: the 06:30 cron this workflow shipped
    with delivered at 07:05-07:30 on all five of its runs — after the 07:00
    routine had already run its own branch check — so the issue could never
    be the channel that informed it. Phase 20 measured it and moved the cron;
    these tests keep it moved.
    """

    # Observed, not assumed. Routine sessions fire at 07:00 UTC (research
    # tier) and ~09:00 (execution tier); every morning PR since 2026-08-14 was
    # opened 07:15-07:30, consistent with a 07:00 start.
    EARLIEST_ROUTINE_HOUR = 7
    # GitHub queues scheduled workflows rather than running them on time. Max
    # observed delay over 24 scheduled runs of this repo's two crons: 232.9
    # minutes. A schedule must clear that, or it races the session.
    MAX_OBSERVED_DELAY_MINUTES = 233

    def _workflow(self):
        return (REPO_ROOT / ".github/workflows/kb-stranded.yml").read_text()

    def _cron_minutes_after_midnight(self):
        for line in self._workflow().splitlines():
            line = line.strip()
            if line.startswith("- cron:"):
                spec = line.split("cron:", 1)[1].strip().strip('"\'')
                minute, hour = spec.split()[:2]
                return int(hour) * 60 + int(minute)
        self.fail("kb-stranded.yml has no cron line")

    def test_the_cron_clears_the_observed_delay_before_the_routine_starts(self):
        latest_delivery = self._cron_minutes_after_midnight() + self.MAX_OBSERVED_DELAY_MINUTES
        self.assertLess(
            latest_delivery,
            self.EARLIEST_ROUTINE_HOUR * 60,
            "even a worst-case delayed run must land before the 07:00 routine; "
            "moving the cron later re-creates the race Phase 20 measured",
        )

    def test_landing_the_work_closes_the_issue_without_waiting_for_the_cron(self):
        # A merge pushes main and deletes the branch, so the run that push
        # triggers sees count=0 and closes. Without it a landed strand leaves
        # a tracking issue claiming work is stranded for up to 24h.
        workflow = self._workflow()
        self.assertIn("push:", workflow)
        self.assertIn("branches: [main]", workflow)

    def test_two_triggers_cannot_open_two_issues(self):
        # `gh issue create` is not idempotent, and the push and schedule
        # triggers can now overlap.
        self.assertIn("concurrency:", self._workflow())


class TestCli(unittest.TestCase):
    def test_reads_a_path_and_prints_title_body_count(self):
        payload = json.dumps([row("claude/x", pr=7)])
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/kb_stranded_issue.py")],
            input=payload, capture_output=True, text=True, check=True,
        )
        out = json.loads(proc.stdout)
        self.assertEqual(set(out), {"title", "body", "count"})
        self.assertEqual(out["count"], 1)
        self.assertEqual(out["title"], ksi.ISSUE_TITLE)

    def test_empty_inventory_is_a_clean_zero(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/kb_stranded_issue.py")],
            input="[]", capture_output=True, text=True, check=True,
        )
        self.assertEqual(json.loads(proc.stdout)["count"], 0)


if __name__ == "__main__":
    unittest.main()
