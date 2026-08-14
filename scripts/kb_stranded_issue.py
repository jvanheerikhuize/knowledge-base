#!/usr/bin/env python3
"""Render a branch inventory as a GitHub issue title + body for stranded work.

    python3 scripts/kb_stranded_issue.py [inventory.json]   # stdin if no path

A *stranded* branch is one a routine session pushed and then ended without
landing: `claude/*`, holding commits that are not on `main`, and quiet long
enough that no session is plausibly still working on it. `AUTONOMY.md` has
carried a prose rule against stranding since 2026-07-31 and a repaired one
since 2026-08-09; `claude/cool-cerf-bb1xow` was stranded on 2026-08-10 anyway,
by a session that believed it had landed and wrote so in `DEBRIEF.md`. Prose
cannot reach a session that already agrees with it, which is what reopened
this detector — see `ROADMAP.md` and [[stranded-branches-need-a-second-channel]].

Pure formatting, no git and no GitHub calls: the workflow that enumerates
branches and owns opening, updating, and closing the issue is
`.github/workflows/kb-stranded.yml`. Same split as `kb_due_issue.py` — the
half that can be unit tested lives here, the half that needs a network lives
in the workflow.

Input is a JSON list, one object per remote branch:

    [{"branch": "claude/foo-abc123",
      "ahead": 2,                       # commits not on main
      "tip": "2026-08-10T09:20:13Z",    # tip commit date, ISO-8601 UTC
      "pr": 55}]                        # open PR number, or null

No third-party dependencies — stdlib only, same as the rest of the KB tooling.
"""
import json
import sys
from datetime import datetime, timezone

ISSUE_TITLE = "Routine sessions: work stranded off main"

# Only branches a routine session creates. A human's branch is not stranded
# work — nobody ended a session on it.
BRANCH_PREFIX = "claude/"

# Measured, not guessed: every one of the 25 legitimately-merged PRs in this
# repo merged within 62 minutes of opening (median 4.4), so 12h clears the
# observed maximum 11-fold and cannot fire on a session still in flight.
# Baseline recorded in ROADMAP.md, "The stranded-branch detector, measured".
STALE_HOURS = 12

# The zero-false-positive property depends on delete-branch-on-merge being on
# for this repo: a *squash* merge leaves the branch's commits off `main`, so a
# squash-merged branch that survived would read as `ahead > 0` forever. All 19
# branches a PR has ever merged here were deleted on the spot, so the case has
# never occurred — but turning that setting off would make this detector lie.

# Branches that satisfy the predicate and always will, because clearing them
# needs a `git push --delete` no routine session can issue (re-probed and
# failed three times: 2026-08-07, 08-08, 08-09). They are reported for
# completeness but never open the issue — a tracking issue nobody in a routine
# can close is the `kb-due` close-branch problem in reverse, and it is the
# reason ROADMAP.md declined to build this detector on 2026-08-09.
#
# A reason is required for every entry, and every entry must be documented in
# AUTONOMY.md's leftover-branch table — both enforced by
# tests/test_kb_stranded_issue.py, so this list cannot be grown quietly to
# silence a real stranding.
ACKNOWLEDGED = {
    "claude/cool-cerf-so8mrh": (
        "content recovered via PR #30 (2026-07-31); conflicts heavily against "
        "the divergence since, so it has no landable diff. Jerry must delete."
    ),
    "claude/cool-cerf-sr8tim": (
        "content recovered via PR #30 (2026-07-31); same — no landable diff "
        "remains. Jerry must delete."
    ),
}

DELETE_COMMAND = "git push origin --delete " + " ".join(sorted(ACKNOWLEDGED))


def _age_hours(tip, now):
    """Hours between an ISO-8601 tip date and `now`. Negative clamps to 0."""
    stamp = datetime.fromisoformat(tip.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return max(0.0, (now - stamp).total_seconds() / 3600.0)


def classify(rows, now=None):
    """Split a branch inventory into (actionable, acknowledged, ignored).

    `actionable` is what the issue is opened for: a `claude/*` branch with
    commits off `main`, quiet for STALE_HOURS, not on the acknowledged list.
    Each row gains an `age_hours` key. Oldest first — the longest-stranded
    branch is the one whose backlog item has been misreported the longest.
    """
    now = now or datetime.now(timezone.utc)
    actionable, acknowledged = [], []
    for row in rows:
        branch = row["branch"]
        if not branch.startswith(BRANCH_PREFIX) or row["ahead"] <= 0:
            # `ahead == 0` is the squash-merge leftover: every line of it is on
            # `main` already, so there is nothing to land and nothing to report.
            continue
        enriched = dict(row, age_hours=_age_hours(row["tip"], now))
        if branch in ACKNOWLEDGED:
            enriched["reason"] = ACKNOWLEDGED[branch]
            acknowledged.append(enriched)
        elif enriched["age_hours"] >= STALE_HOURS:
            actionable.append(enriched)
    actionable.sort(key=lambda r: -r["age_hours"])
    acknowledged.sort(key=lambda r: -r["age_hours"])
    return actionable, acknowledged


def _describe(row):
    days = row["age_hours"] / 24.0
    age = f"{days:.1f}d" if days >= 1 else f"{row['age_hours']:.0f}h"
    commits = "1 commit" if row["ahead"] == 1 else f"{row['ahead']} commits"
    return age, commits


def render(rows, now=None):
    """rows: the inventory shape above. Returns (title, body, count).

    `count` is the actionable total only, so the workflow closes the issue
    when the acknowledged branches are all that is left.
    """
    actionable, acknowledged = classify(rows, now)
    lines = [
        "A routine session pushed these and ended without landing them. Work "
        "on a branch is invisible: its `DEBRIEF.md` line and its backlog "
        "checkbox are not on `main`, so the next session reads the item as "
        "unstarted and redoes it.",
        "",
        "**Land each one** — open a PR and merge it, or merge the PR already "
        "open. `AUTONOMY.md`: the post-mandate gate is on what you may "
        "*start*, not what you may *land*. Merging also deletes the branch, "
        "which is why no branch a PR ever merged is still here.",
        "",
    ]
    for row in actionable:
        age, commits = _describe(row)
        pr = f" — PR #{row['pr']} open, unmerged" if row.get("pr") else " — no PR"
        lines.append(
            f"- [ ] `{row['branch']}` — {commits} off `main`, quiet {age}{pr}"
        )
    if acknowledged:
        lines.extend([
            "",
            "### Acknowledged — not counted, only Jerry can clear these",
            "",
        ])
        for row in acknowledged:
            age, commits = _describe(row)
            lines.append(
                f"- `{row['branch']}` — {commits} off `main`, quiet {age} — "
                f"{row['reason']}"
            )
        lines.extend(["", f"    {DELETE_COMMAND}"])
    lines.extend([
        "",
        "_Generated by `kb_stranded_issue.py`; this issue is opened, updated, "
        "or closed automatically by the `kb-stranded` workflow — editing it by "
        "hand will be overwritten on the next run._",
    ])
    return ISSUE_TITLE, "\n".join(lines), len(actionable)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    with (open(path) if path else sys.stdin) as f:
        rows = json.load(f)
    title, body, count = render(rows)
    print(json.dumps({"title": title, "body": body, "count": count}))


if __name__ == "__main__":
    main()
