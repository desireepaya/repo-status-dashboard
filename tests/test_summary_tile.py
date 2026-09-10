"""The summary strip must not report good news it has not verified."""

from datetime import datetime, timezone

import pytest

from repo_status.models import CheckSummary, Dashboard, PRSummary, RepoReport

NOW = datetime.now(timezone.utc)


def repo(workflow_count, checks=None, error=None):
    prs = []
    if checks is not None:
        prs = [
            PRSummary(
                number=1,
                title="t",
                author="a",
                url="u",
                draft=False,
                updated_at=NOW,
                mergeable_state="clean",
                review_state="no_review",
                reviewers=(),
                checks=checks,
            )
        ]
    return RepoReport(
        slug="o/n",
        display_name="n",
        prs=prs,
        workflow_count=workflow_count,
        error=error,
    )


def tile(*repos):
    return Dashboard(repos=list(repos), generated_at=NOW).check_tile


def test_failures_are_counted_and_flagged():
    t = tile(repo(2, CheckSummary(passed=1, failed=3)))
    assert (t.value, t.label, t.alert) == ("3", "failing checks", True)


def test_a_single_failure_is_singular():
    assert tile(repo(2, CheckSummary(failed=1))).label == "failing check"


def test_zero_failures_is_only_claimed_when_checks_actually_ran():
    t = tile(repo(2, CheckSummary(passed=4)))
    assert (t.value, t.label, t.alert) == ("0", "failing checks", False)


def test_no_ci_anywhere_says_so():
    """The case the live page hits: nothing failed because nothing runs."""
    assert tile(repo(0)).label == "checks configured"


def test_ci_configured_but_nothing_reported():
    assert tile(repo(3)).label == "checks reported"


@pytest.mark.parametrize(
    "repos",
    [
        # Unknown count: cannot claim CI is absent.
        (lambda: (repo(None),)),
        # One confirmed zero is not enough while another is unknown.
        (lambda: (repo(0), repo(None))),
        # No repos at all proves nothing either way.
        (lambda: ()),
    ],
)
def test_unconfirmed_counts_fall_back_to_the_weaker_claim(repos):
    assert tile(*repos()).label == "checks reported"


def test_unreachable_repos_do_not_block_a_confirmed_zero():
    assert tile(repo(0), repo(None, error="boom")).label == "checks configured"
