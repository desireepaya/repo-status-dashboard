"""Collector behaviour: what gets read from the API and how it is reduced."""

import pytest

from repo_status.config import RepoConfig


def test_open_prs_are_sorted_newest_first(report):
    assert [pr.number for pr in report.prs] == [12, 11, 9, 8]


def test_draft_and_ready_counts(report):
    assert report.open_pr_count == 4
    assert report.draft_pr_count == 1
    assert report.ready_pr_count == 3


@pytest.mark.parametrize(
    "number,passed,failed,pending,other",
    [
        # cancelled is real but not a failure, so it lands in `other`
        (12, 1, 2, 0, 1),
        (11, 1, 0, 1, 0),
        (9, 2, 0, 0, 0),
        (8, 0, 0, 0, 0),
    ],
)
def test_check_runs_are_bucketed(prs, number, passed, failed, pending, other):
    checks = prs[number].checks
    assert (checks.passed, checks.failed, checks.pending, checks.other) == (
        passed,
        failed,
        pending,
        other,
    )


@pytest.mark.parametrize(
    "number,state",
    [(12, "failing"), (11, "pending"), (9, "passing"), (8, "none")],
)
def test_check_state_is_worst_case(prs, number, state):
    assert prs[number].checks.state == state


@pytest.mark.parametrize(
    "number,review_state",
    [
        (12, "changes_requested"),
        (11, "no_review"),
        # A later approval supersedes an earlier changes-requested.
        (9, "approved"),
        # A dismissed approval leaves no verdict behind.
        (8, "no_review"),
    ],
)
def test_review_state_is_derived_from_the_reviews_list(prs, number, review_state):
    assert prs[number].review_state == review_state


def test_requested_reviewers_are_captured(prs):
    assert prs[12].reviewers == ("reviewer-one",)
    assert prs[9].reviewers == ()


def test_only_dirty_counts_as_conflicts(prs):
    assert prs[9].has_conflicts is True
    assert prs[12].has_conflicts is False


def test_repo_metadata_is_read(report):
    assert report.default_branch == "main"
    assert report.description.startswith("Multi-account AWS Organization")
    assert report.error is None


def test_repo_state_is_worst_case_across_prs(report):
    assert report.failing_check_count == 2
    assert report.state == "failing"


def test_disabled_workflows_are_not_counted(report):
    assert report.workflow_count == 1


def test_unreachable_repo_is_recorded_not_raised(unreachable):
    assert unreachable.error is not None
    assert unreachable.state == "error"
    assert unreachable.ok is False


def test_unreachable_repo_has_unknown_workflow_count(unreachable):
    """None, not 0. A zero here would wrongly claim no CI is configured."""
    assert unreachable.workflow_count is None


def test_recent_commits_show_only_the_first_message_line(report):
    first = report.recent_commits[0]
    assert first.title == "Add org trail"
    assert "Longer body" not in first.title


def test_recent_commit_sha_is_shortened(report):
    assert report.recent_commits[0].short_sha == "aaaaaaa"


def test_commit_author_falls_back_when_no_account_is_linked(report):
    assert report.recent_commits[0].author == "desireepaya"
    assert report.recent_commits[1].author == "Unlinked Contributor"


def test_last_commit_is_the_newest(report):
    assert report.last_commit_at == report.recent_commits[0].committed_at


def test_repo_with_no_commits_is_not_an_error(collector):
    """GitHub answers 409 for an empty repo. That is nothing to show, not a fault."""
    empty = collector.collect(RepoConfig(slug="empty/repo", display_name="Empty"))
    assert empty.recent_commits == []
    assert empty.error is None
    assert empty.last_commit_at is None
