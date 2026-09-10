"""Collect pending-change data from the GitHub REST API.

Plain httpx rather than PyGithub: the dependency surface stays small and the
responses are trivial to stub, which matters because the primary target repo
often has zero open PRs — the populated render path has to be exercisable
without waiting for real PRs to exist.

Requests per repo: 1 (repo metadata) + 1 (PR list) + 3 per open PR
(detail for mergeable_state, reviews, check-runs). Comfortably inside the
1,000 req/hr per-repo GITHUB_TOKEN ceiling on a daily cron.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from ..config import RepoConfig
from ..models import (
    FAILED_CONCLUSIONS,
    PASSED_CONCLUSIONS,
    CheckSummary,
    PRSummary,
    RepoReport,
)

API_BASE = "https://api.github.com"
_PER_PAGE = 100


class GitHubError(Exception):
    """Raised for failures that should stop the whole build.

    Per-repo problems (404, no access) are recorded on the RepoReport instead,
    so one bad entry in repos.yaml does not take down the dashboard.
    """


class GitHubCollector:
    def __init__(
        self,
        token: str,
        client: httpx.Client | None = None,
        api_base: str = API_BASE,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(20.0),
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Authorization": f"Bearer {token}",
                "User-Agent": "repo-status-dashboard",
            },
        )

    def __enter__(self) -> GitHubCollector:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # ---- HTTP -----------------------------------------------------------

    def _get(self, path: str, **params: object) -> httpx.Response:
        url = path if path.startswith("http") else f"{self.api_base}{path}"
        try:
            response = self._client.get(url, params=params or None)
        except httpx.HTTPError as exc:
            raise GitHubError(f"request to {url} failed: {exc}") from exc

        if response.status_code == 401:
            raise GitHubError(
                "GitHub rejected the token (401). Check GH_TOKEN / GITHUB_TOKEN."
            )
        if response.status_code == 403 and "rate limit" in response.text.lower():
            raise GitHubError("GitHub API rate limit exceeded (403).")
        return response

    def _paginate(self, path: str, key: str | None = None, **params: object) -> list:
        """Follow Link headers, returning the concatenated items.

        `key` names the field holding the list for envelope responses such as
        check-runs; omit it for endpoints that return a bare array.
        """
        items: list = []
        url: str | None = path
        page_params = {**params, "per_page": _PER_PAGE}

        while url:
            response = self._get(url, **page_params)
            response.raise_for_status()
            payload = response.json()
            batch = payload.get(key, []) if key else payload
            items.extend(batch)

            # Subsequent Link URLs already carry their query string.
            url = response.links.get("next", {}).get("url")
            page_params = {}

        return items

    # ---- Collection -----------------------------------------------------

    def collect(self, repo: RepoConfig) -> RepoReport:
        """Build a RepoReport, capturing per-repo failures as `error`."""
        report = RepoReport(slug=repo.slug, display_name=repo.display_name)

        try:
            meta = self._get(f"/repos/{repo.slug}")
            if meta.status_code == 404:
                report.error = "repository not found, or the token cannot see it"
                return report
            meta.raise_for_status()
            info = meta.json()

            report.url = info.get("html_url") or f"https://github.com/{repo.slug}"
            report.description = info.get("description") or ""
            report.default_branch = info.get("default_branch") or ""

            pulls = self._paginate(f"/repos/{repo.slug}/pulls", state="open")
            report.prs = [self._build_pr(repo.slug, pr) for pr in pulls]
            report.prs.sort(key=lambda pr: pr.updated_at, reverse=True)

        except GitHubError:
            raise
        except httpx.HTTPStatusError as exc:
            report.error = f"GitHub API error {exc.response.status_code}"
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            report.error = f"could not collect: {exc}"

        return report

    def _build_pr(self, slug: str, pr: dict) -> PRSummary:
        number = pr["number"]
        head_sha = (pr.get("head") or {}).get("sha", "")

        # mergeable_state is only present on the single-PR endpoint.
        detail_response = self._get(f"/repos/{slug}/pulls/{number}")
        detail = detail_response.json() if detail_response.is_success else {}

        reviewers = tuple(
            user.get("login", "")
            for user in (pr.get("requested_reviewers") or [])
            if user.get("login")
        )

        return PRSummary(
            number=number,
            title=pr.get("title") or f"#{number}",
            author=(pr.get("user") or {}).get("login", "unknown"),
            url=pr.get("html_url") or f"https://github.com/{slug}/pull/{number}",
            draft=bool(pr.get("draft")),
            updated_at=_parse_ts(pr.get("updated_at")),
            mergeable_state=detail.get("mergeable_state") or "unknown",
            review_state=self._review_state(slug, number, reviewers),
            reviewers=reviewers,
            checks=self._check_summary(slug, head_sha),
        )

    def _review_state(self, slug: str, number: int, reviewers: tuple[str, ...]) -> str:
        """Derive a review decision from the reviews list.

        REST has no `reviewDecision` field (that is GraphQL only), so take the
        latest meaningful review per reviewer and reduce. Reviews arrive in
        submission order, so a later entry overwrites an earlier one.
        """
        reviews = self._paginate(f"/repos/{slug}/pulls/{number}/reviews")

        latest: dict[str, str] = {}
        for review in reviews:
            state = (review.get("state") or "").upper()
            login = (review.get("user") or {}).get("login")
            if not login or state in {"COMMENTED", "PENDING"}:
                continue
            if state == "DISMISSED":
                latest.pop(login, None)
                continue
            latest[login] = state

        states = set(latest.values())
        if "CHANGES_REQUESTED" in states:
            return "changes_requested"
        if "APPROVED" in states:
            return "approved"
        if reviewers:
            return "review_requested"
        return "no_review"

    def _check_summary(self, slug: str, head_sha: str) -> CheckSummary:
        """Summarise check-runs on the PR head.

        Note: this covers the Checks API only, not legacy commit statuses.
        """
        if not head_sha:
            return CheckSummary()

        runs = self._paginate(
            f"/repos/{slug}/commits/{head_sha}/check-runs", key="check_runs"
        )

        passed = failed = pending = other = 0
        for run in runs:
            if run.get("status") != "completed":
                pending += 1
                continue
            conclusion = run.get("conclusion") or ""
            if conclusion in PASSED_CONCLUSIONS:
                passed += 1
            elif conclusion in FAILED_CONCLUSIONS:
                failed += 1
            else:
                other += 1

        return CheckSummary(passed=passed, failed=failed, pending=pending, other=other)


def _parse_ts(value: str | None) -> datetime:
    """Parse a GitHub ISO-8601 timestamp into an aware UTC datetime."""
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
