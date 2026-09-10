"""Stubbed GitHub responses shared by the test suite.

Everything runs through httpx.MockTransport, so the tests need no network and
no token. That is not just convenience: the repo this dashboard tracks usually
has zero open pull requests, so most of the interesting states cannot be
reached with live data at all.
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from repo_status.collectors.github import GitHubCollector
from repo_status.config import RepoConfig

NOW = datetime.now(timezone.utc)


def ts(days: int) -> str:
    return (NOW - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


REPO = {
    "html_url": "https://github.com/desireepaya/aws-security-baseline",
    "description": "Multi-account AWS Organization with preventative guardrails.",
    "default_branch": "main",
}

PULLS = [
    {
        "number": 12,
        "title": "Add GuardDuty delegated administration",
        "user": {"login": "desireepaya"},
        "html_url": "https://github.com/x/y/pull/12",
        "draft": False,
        "updated_at": ts(1),
        "head": {"sha": "sha-failing"},
        "requested_reviewers": [{"login": "reviewer-one"}],
    },
    {
        "number": 11,
        "title": "WIP: Identity Center permission sets",
        "user": {"login": "desireepaya"},
        "html_url": "https://github.com/x/y/pull/11",
        "draft": True,
        "updated_at": ts(4),
        "head": {"sha": "sha-pending"},
        "requested_reviewers": [],
    },
    {
        "number": 9,
        "title": "Tighten region containment SCP",
        "user": {"login": "contributor"},
        "html_url": "https://github.com/x/y/pull/9",
        "draft": False,
        "updated_at": ts(40),
        "head": {"sha": "sha-passing"},
        "requested_reviewers": [],
    },
    {
        "number": 8,
        "title": "Bootstrap remote state",
        "user": {"login": "desireepaya"},
        "html_url": "https://github.com/x/y/pull/8",
        "draft": False,
        "updated_at": ts(50),
        "head": {"sha": "sha-none"},
        "requested_reviewers": [],
    },
]

# mergeable_state only appears on the single-PR endpoint.
DETAIL = {
    12: {"mergeable_state": "blocked"},
    11: {"mergeable_state": "draft"},
    9: {"mergeable_state": "dirty"},
    8: {"mergeable_state": "clean"},
}

REVIEWS = {
    12: [{"user": {"login": "reviewer-one"}, "state": "CHANGES_REQUESTED"}],
    11: [],
    # A later approval from the same reviewer supersedes the earlier request.
    # A COMMENTED review is not a verdict and must be ignored.
    9: [
        {"user": {"login": "reviewer-one"}, "state": "CHANGES_REQUESTED"},
        {"user": {"login": "reviewer-one"}, "state": "APPROVED"},
        {"user": {"login": "reviewer-two"}, "state": "COMMENTED"},
    ],
    # A dismissed approval leaves no verdict behind.
    8: [
        {"user": {"login": "reviewer-one"}, "state": "APPROVED"},
        {"user": {"login": "reviewer-one"}, "state": "DISMISSED"},
    ],
}

CHECKS = {
    "sha-failing": [
        {"status": "completed", "conclusion": "success"},
        {"status": "completed", "conclusion": "failure"},
        {"status": "completed", "conclusion": "timed_out"},
        {"status": "completed", "conclusion": "cancelled"},
    ],
    "sha-pending": [
        {"status": "in_progress", "conclusion": None},
        {"status": "completed", "conclusion": "success"},
    ],
    "sha-passing": [
        {"status": "completed", "conclusion": "success"},
        {"status": "completed", "conclusion": "skipped"},
    ],
    "sha-none": [],
}

COMMITS = [
    {
        "sha": "aaaaaaaabbbbbbbbcccccccc",
        "html_url": "https://github.com/x/y/commit/aaaaaaa",
        "author": {"login": "desireepaya"},
        "commit": {
            "message": "Add org trail\n\nLonger body that should not render.",
            "author": {"name": "Desiree Paya", "date": ts(2)},
        },
    },
    {
        "sha": "ddddddddeeeeeeeeffffffff",
        "html_url": "https://github.com/x/y/commit/ddddddd",
        # Null when the commit email is not linked to a GitHub account.
        "author": None,
        "commit": {
            "message": "Tighten SCP",
            "author": {"name": "Unlinked Contributor", "date": ts(6)},
        },
    },
]

WORKFLOWS = {
    "total_count": 2,
    "workflows": [
        {"name": "ci", "state": "active"},
        {"name": "old", "state": "disabled_manually"},
    ],
}


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path

    if path == "/repos/bad/repo":
        return httpx.Response(404, json={"message": "Not Found"})
    if path == "/repos/empty/repo/commits":
        # What GitHub returns for a repo with no commits yet.
        return httpx.Response(409, json={"message": "Git Repository is empty."})
    if path.endswith("/commits"):
        return httpx.Response(200, json=COMMITS)
    if path.endswith("/actions/workflows"):
        return httpx.Response(200, json=WORKFLOWS)
    if path.endswith("/check-runs"):
        sha = path.split("/commits/")[1].split("/")[0]
        runs = CHECKS[sha]
        return httpx.Response(200, json={"total_count": len(runs), "check_runs": runs})
    if path.endswith("/reviews"):
        number = int(path.split("/pulls/")[1].split("/")[0])
        return httpx.Response(200, json=REVIEWS[number])
    if "/pulls/" in path:
        return httpx.Response(200, json=DETAIL[int(path.rsplit("/pulls/", 1)[1])])
    if path.endswith("/pulls"):
        return httpx.Response(200, json=PULLS)
    return httpx.Response(200, json=REPO)


@pytest.fixture
def collector():
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GitHubCollector(token="stub", client=client)


@pytest.fixture
def report(collector):
    """A fully populated repo report."""
    return collector.collect(
        RepoConfig(slug="desireepaya/aws-security-baseline", display_name="Baseline")
    )


@pytest.fixture
def prs(report):
    return {pr.number: pr for pr in report.prs}


@pytest.fixture
def unreachable(collector):
    return collector.collect(RepoConfig(slug="bad/repo", display_name="Broken Repo"))
