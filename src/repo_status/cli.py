"""`repo-status` command line entrypoint."""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import os
import socketserver
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import DEFAULT_STATIC_DIR, DEFAULT_TEMPLATES_DIR, __version__
from .collectors.github import GitHubCollector, GitHubError
from .config import ConfigError, load_config
from .models import Dashboard
from .render import render

# GH_TOKEN locally (from `gh auth token`), GITHUB_TOKEN in Actions.
_TOKEN_VARS = ("GH_TOKEN", "GITHUB_TOKEN")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "generate":
        return _generate(args)

    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-status",
        description="Generate a static dashboard of pending repo changes.",
    )
    parser.add_argument("--version", action="version", version=__version__)

    subparsers = parser.add_subparsers(dest="command")
    generate = subparsers.add_parser("generate", help="collect data and render HTML")
    generate.add_argument(
        "--config",
        default="config/repos.yaml",
        help="path to repos.yaml (default: config/repos.yaml)",
    )
    generate.add_argument(
        "--out",
        default="dist",
        help="output directory (default: dist)",
    )
    generate.add_argument(
        "--templates",
        default=str(DEFAULT_TEMPLATES_DIR),
        help="templates directory",
    )
    generate.add_argument(
        "--static",
        default=str(DEFAULT_STATIC_DIR),
        help="static assets directory",
    )
    generate.add_argument(
        "--serve",
        action="store_true",
        help="serve the output directory after rendering, for local preview",
    )
    generate.add_argument(
        "--port",
        type=int,
        default=8000,
        help="port for --serve (default: 8000)",
    )
    return parser


def _generate(args: argparse.Namespace) -> int:
    try:
        repos = load_config(args.config)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    token = _resolve_token()
    if not token:
        print(
            "error: no GitHub token found. Set one of "
            f"{' / '.join(_TOKEN_VARS)}.\n"
            "  locally:  GH_TOKEN=$(gh auth token) repo-status generate",
            file=sys.stderr,
        )
        return 2

    print(f"collecting {len(repos)} repo(s)...", file=sys.stderr)
    reports = []
    try:
        with GitHubCollector(token=token) as collector:
            for repo in repos:
                report = collector.collect(repo)
                status = report.error or f"{report.open_pr_count} open PR(s)"
                print(f"  {repo.slug}: {status}", file=sys.stderr)
                reports.append(report)
    except GitHubError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    dashboard = Dashboard(repos=reports, generated_at=datetime.now(timezone.utc))

    try:
        index_path = render(
            dashboard,
            out_dir=args.out,
            templates_dir=args.templates,
            static_dir=args.static,
        )
    except (FileNotFoundError, OSError) as exc:
        print(f"error: render failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"wrote {index_path} "
        f"({dashboard.repo_count} repos, {dashboard.open_pr_count} open PRs, "
        f"{dashboard.failing_check_count} failing checks)",
        file=sys.stderr,
    )

    if dashboard.error_count:
        print(
            f"warning: {dashboard.error_count} repo(s) could not be collected",
            file=sys.stderr,
        )

    if args.serve:
        _serve(Path(args.out), args.port)

    return 0


def _resolve_token() -> str | None:
    for var in _TOKEN_VARS:
        value = os.environ.get(var)
        if value:
            return value
    return None


def _serve(directory: Path, port: int) -> None:
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(directory)
    )

    class ReuseAddrServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReuseAddrServer(("127.0.0.1", port), handler) as httpd:
        print(f"serving {directory} at http://127.0.0.1:{port}/", file=sys.stderr)
        print("ctrl-c to stop", file=sys.stderr)
        with contextlib.suppress(KeyboardInterrupt):
            httpd.serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
