"""Data shapes rendered by the dashboard.

These are deliberately plain dataclasses: the collector builds them from API
responses, the templates read them, and nothing else touches them. That keeps
the render path stubbable without a live GitHub token.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Check-run conclusions grouped into the three states worth showing on a card.
# Anything else (cancelled, stale) lands in `other` — real but not actionable.
PASSED_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})
FAILED_CONCLUSIONS = frozenset(
    {"failure", "timed_out", "action_required", "startup_failure"}
)


@dataclass(frozen=True)
class Tile:
    """A single figure in the summary strip."""

    value: str
    label: str
    alert: bool = False


@dataclass(frozen=True)
class CheckSummary:
    """Roll-up of the check-runs on a PR's head commit."""

    passed: int = 0
    failed: int = 0
    pending: int = 0
    other: int = 0

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.pending + self.other

    @property
    def state(self) -> str:
        """Single worst-case label, for badge styling."""
        if self.total == 0:
            return "none"
        if self.failed:
            return "failing"
        if self.pending:
            return "pending"
        return "passing"

    @property
    def label(self) -> str:
        if self.total == 0:
            return "no checks"
        parts = []
        if self.passed:
            parts.append(f"{self.passed} passed")
        if self.failed:
            parts.append(f"{self.failed} failed")
        if self.pending:
            parts.append(f"{self.pending} pending")
        if self.other:
            parts.append(f"{self.other} other")
        return ", ".join(parts)


@dataclass(frozen=True)
class PRSummary:
    number: int
    title: str
    author: str
    url: str
    draft: bool
    updated_at: datetime
    # GitHub's mergeable_state: clean | dirty | blocked | behind | unstable |
    # draft | unknown. "dirty" is the one that means conflicts.
    mergeable_state: str
    # Derived from the reviews list: approved | changes_requested |
    # review_requested | no_review
    review_state: str
    reviewers: tuple[str, ...]
    checks: CheckSummary

    @property
    def has_conflicts(self) -> bool:
        return self.mergeable_state == "dirty"

    @property
    def review_label(self) -> str:
        return {
            "approved": "approved",
            "changes_requested": "changes requested",
            "review_requested": "review requested",
            "no_review": "no review",
        }.get(self.review_state, self.review_state)


@dataclass
class RepoReport:
    slug: str
    display_name: str
    url: str = ""
    description: str = ""
    default_branch: str = ""
    prs: list[PRSummary] = field(default_factory=list)
    # Number of active CI workflows in the repo. None means we could not
    # determine it, which is deliberately distinct from a known zero: only a
    # known zero justifies saying "no checks configured".
    workflow_count: int | None = None
    # Set when this repo could not be collected. The rest of the dashboard
    # still renders. One unreachable repo must not fail the whole build.
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def open_pr_count(self) -> int:
        return len(self.prs)

    @property
    def ready_pr_count(self) -> int:
        return sum(1 for pr in self.prs if not pr.draft)

    @property
    def draft_pr_count(self) -> int:
        return sum(1 for pr in self.prs if pr.draft)

    @property
    def failing_check_count(self) -> int:
        return sum(pr.checks.failed for pr in self.prs)

    @property
    def check_run_count(self) -> int:
        return sum(pr.checks.total for pr in self.prs)

    @property
    def state(self) -> str:
        """Card-level status, worst-case across the repo's PRs."""
        if self.error:
            return "error"
        if self.failing_check_count:
            return "failing"
        if any(pr.checks.state == "pending" for pr in self.prs):
            return "pending"
        if self.prs:
            return "open"
        return "clear"


@dataclass
class Dashboard:
    repos: list[RepoReport]
    generated_at: datetime

    @property
    def repo_count(self) -> int:
        return len(self.repos)

    @property
    def open_pr_count(self) -> int:
        return sum(r.open_pr_count for r in self.repos)

    @property
    def failing_check_count(self) -> int:
        return sum(r.failing_check_count for r in self.repos)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.repos if r.error)

    @property
    def check_run_count(self) -> int:
        return sum(r.check_run_count for r in self.repos)

    @property
    def check_tile(self) -> Tile:
        """The summary figure for CI, worded for what was actually observed.

        "0 failing checks" is misleading when nothing ran: it reads as a pass
        when the truth is that there was nothing to report, or no CI at all.
        Only a confirmed zero across every reachable repo justifies the
        stronger "0 checks configured".
        """
        failing = self.failing_check_count
        if failing:
            noun = "check" if failing == 1 else "checks"
            return Tile(str(failing), f"failing {noun}", alert=True)

        if self.check_run_count:
            return Tile("0", "failing checks")

        reachable = [r for r in self.repos if r.ok]
        counted = [r for r in reachable if r.workflow_count is not None]
        if reachable and len(counted) == len(reachable):
            if not any(r.workflow_count for r in counted):
                return Tile("0", "checks configured")

        return Tile("0", "checks reported")
