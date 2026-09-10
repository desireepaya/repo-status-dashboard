"""Render the Dashboard to dist/index.html plus copied static assets."""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from . import DEFAULT_STATIC_DIR, DEFAULT_TEMPLATES_DIR
from .models import Dashboard


def build_environment(templates_dir: Path) -> Environment:
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["utc_stamp"] = utc_stamp
    env.filters["relative_time"] = relative_time
    return env


def render(
    dashboard: Dashboard,
    out_dir: str | Path,
    templates_dir: str | Path = DEFAULT_TEMPLATES_DIR,
    static_dir: str | Path = DEFAULT_STATIC_DIR,
) -> Path:
    """Write the dashboard to `out_dir`, returning the index.html path."""
    out_dir = Path(out_dir)
    templates_dir = Path(templates_dir)
    static_dir = Path(static_dir)

    if not templates_dir.is_dir():
        raise FileNotFoundError(f"templates directory not found: {templates_dir}")

    env = build_environment(templates_dir)
    html = env.get_template("index.html.j2").render(dashboard=dashboard)

    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "index.html"
    index_path.write_text(html, encoding="utf-8")

    if static_dir.is_dir():
        shutil.copytree(static_dir, out_dir / "static", dirs_exist_ok=True)

    return index_path


def utc_stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def relative_time(value: datetime) -> str:
    """Coarse "3 days ago" phrasing — precision beyond this is noise here."""
    delta = datetime.now(timezone.utc) - value.astimezone(timezone.utc)
    seconds = int(delta.total_seconds())

    if seconds < 0:
        return "just now"
    if seconds < 90:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 30:
        return f"{days}d ago"
    months = days // 30
    if months < 12:
        return f"{months}mo ago"
    return f"{days // 365}y ago"
