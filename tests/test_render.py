"""The rendered page must actually contain what the data says."""

from datetime import datetime, timezone

import pytest

from repo_status.models import Dashboard
from repo_status.render import relative_time, render

NOW = datetime.now(timezone.utc)


@pytest.fixture
def page(tmp_path, report, unreachable):
    dashboard = Dashboard(repos=[report, unreachable], generated_at=NOW)
    index = render(dashboard, out_dir=tmp_path)
    return index.read_text(), tmp_path


@pytest.mark.parametrize(
    "needle",
    [
        "Add GuardDuty delegated administration",
        "changes requested",
        "1 passed, 2 failed, 1 other",
        "conflicts",
        "draft",
        "Add org trail",
        "aaaaaaa",
        "Unlinked Contributor",
        "last commit",
        "Recent commits",
        "Broken Repo",
        "unreachable",
        "Infra health",
    ],
)
def test_page_contains(page, needle):
    html, _ = page
    assert needle in html


def test_commit_body_is_not_rendered(page):
    html, _ = page
    assert "Longer body" not in html


def test_static_assets_are_copied(page):
    _, out_dir = page
    assert (out_dir / "static" / "style.css").is_file()


def test_dashboard_totals(report, unreachable):
    dashboard = Dashboard(repos=[report, unreachable], generated_at=NOW)
    assert dashboard.repo_count == 2
    assert dashboard.open_pr_count == 4
    assert dashboard.failing_check_count == 2
    assert dashboard.error_count == 1


@pytest.mark.parametrize(
    "seconds,expected",
    [(30, "just now"), (600, "10m ago"), (7200, "2h ago"), (172800, "2d ago")],
)
def test_relative_time(seconds, expected):
    from datetime import timedelta

    assert relative_time(NOW - timedelta(seconds=seconds)) == expected
