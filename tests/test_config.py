"""Config loading.

A bad repos.yaml is the most likely way this project breaks in normal use,
since adding a repo is the one routine edit. Every rejection path is checked,
because a config error that slips through would publish a half-empty page
rather than failing loudly.
"""

import pytest

from repo_status.config import ConfigError, RepoConfig, load_config

VALID = """
repos:
  - slug: desireepaya/aws-security-baseline
    display_name: AWS Security Baseline
  - slug: desireepaya/other-repo
"""


def write(tmp_path, text, name="repos.yaml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ---- accepted ----------------------------------------------------------


def test_loads_configured_repos(tmp_path):
    repos = load_config(write(tmp_path, VALID))
    assert [r.slug for r in repos] == [
        "desireepaya/aws-security-baseline",
        "desireepaya/other-repo",
    ]


def test_display_name_is_used_when_given(tmp_path):
    repos = load_config(write(tmp_path, VALID))
    assert repos[0].display_name == "AWS Security Baseline"


def test_display_name_defaults_to_the_repo_name(tmp_path):
    repos = load_config(write(tmp_path, VALID))
    assert repos[1].display_name == "other-repo"


def test_owner_and_name_are_split_from_the_slug():
    repo = RepoConfig(slug="owner/name", display_name="n")
    assert (repo.owner, repo.name) == ("owner", "name")


@pytest.mark.parametrize(
    "slug",
    [
        "owner/name",
        "owner-with-hyphen/name-with-hyphen",
        "owner.dot/name.dot",
        "owner_score/name_score",
        "Owner123/Name456",
    ],
)
def test_accepted_slug_shapes(tmp_path, slug):
    config = f"repos:\n  - slug: {slug}\n"
    assert load_config(write(tmp_path, config))[0].slug == slug


# ---- rejected ----------------------------------------------------------


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")


def test_invalid_yaml(tmp_path):
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_config(write(tmp_path, "repos: [unclosed\n"))


def test_empty_file(tmp_path):
    with pytest.raises(ConfigError, match="empty"):
        load_config(write(tmp_path, ""))


def test_top_level_must_be_a_mapping(tmp_path):
    with pytest.raises(ConfigError, match="top level must be a mapping"):
        load_config(write(tmp_path, "- just\n- a\n- list\n"))


def test_missing_repos_key(tmp_path):
    with pytest.raises(ConfigError, match="missing required 'repos'"):
        load_config(write(tmp_path, "something_else: true\n"))


@pytest.mark.parametrize("body", ["repos: []\n", "repos: not-a-list\n"])
def test_repos_must_be_a_non_empty_list(tmp_path, body):
    with pytest.raises(ConfigError, match="non-empty list"):
        load_config(write(tmp_path, body))


def test_entry_must_be_a_mapping(tmp_path):
    with pytest.raises(ConfigError, match="each entry must be a mapping"):
        load_config(write(tmp_path, "repos:\n  - just-a-string\n"))


def test_missing_slug(tmp_path):
    with pytest.raises(ConfigError, match="missing required 'slug'"):
        load_config(write(tmp_path, "repos:\n  - display_name: No Slug\n"))


@pytest.mark.parametrize(
    "slug",
    [
        "no-slash",
        "too/many/slashes",
        "/leading-slash",
        "trailing-slash/",
        "spaces in/name",
    ],
)
def test_malformed_slugs_are_rejected(tmp_path, slug):
    config = f'repos:\n  - slug: "{slug}"\n'
    with pytest.raises(ConfigError, match="must be 'owner/name'"):
        load_config(write(tmp_path, config))


def test_duplicate_slugs_are_rejected(tmp_path):
    config = "repos:\n  - slug: a/b\n  - slug: a/b\n"
    with pytest.raises(ConfigError, match="duplicate slug"):
        load_config(write(tmp_path, config))


def test_display_name_must_be_a_string(tmp_path):
    config = "repos:\n  - slug: a/b\n    display_name: [1, 2]\n"
    with pytest.raises(ConfigError, match="'display_name' must be a string"):
        load_config(write(tmp_path, config))


def test_error_names_the_offending_entry(tmp_path):
    """Index in the message, so a long file points at the right line."""
    config = "repos:\n  - slug: good/one\n  - slug: bad\n"
    with pytest.raises(ConfigError, match=r"repos\[1\]"):
        load_config(write(tmp_path, config))
