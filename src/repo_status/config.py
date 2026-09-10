"""Loading and validation for config/repos.yaml."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# owner/name — GitHub allows alphanumerics, hyphen, underscore and dot.
_SLUG_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


class ConfigError(Exception):
    """Raised for a malformed or unreadable config file."""


@dataclass(frozen=True)
class RepoConfig:
    slug: str
    display_name: str

    @property
    def owner(self) -> str:
        return self.slug.split("/", 1)[0]

    @property
    def name(self) -> str:
        return self.slug.split("/", 1)[1]


def load_config(path: str | Path) -> list[RepoConfig]:
    """Read repos.yaml and return the configured repos.

    Raises ConfigError with an actionable message on any problem — a bad
    config should fail the build loudly rather than publish a half-empty page.
    """
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc

    if raw is None:
        raise ConfigError(f"{path}: file is empty")
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping with a 'repos' key")

    repos = raw.get("repos")
    if repos is None:
        raise ConfigError(f"{path}: missing required 'repos' key")
    if not isinstance(repos, list) or not repos:
        raise ConfigError(f"{path}: 'repos' must be a non-empty list")

    parsed: list[RepoConfig] = []
    seen: set[str] = set()

    for index, entry in enumerate(repos):
        where = f"{path}: repos[{index}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: each entry must be a mapping")

        slug = entry.get("slug")
        if not slug or not isinstance(slug, str):
            raise ConfigError(f"{where}: missing required 'slug'")
        if not _SLUG_RE.match(slug):
            raise ConfigError(f"{where}: slug must be 'owner/name', got {slug!r}")
        if slug in seen:
            raise ConfigError(f"{where}: duplicate slug {slug!r}")
        seen.add(slug)

        display_name = entry.get("display_name") or slug.split("/", 1)[1]
        if not isinstance(display_name, str):
            raise ConfigError(f"{where}: 'display_name' must be a string")

        parsed.append(RepoConfig(slug=slug, display_name=display_name))

    return parsed
