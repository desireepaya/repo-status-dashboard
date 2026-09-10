# Plan: `repo-status-dashboard`

## Context

You want a shareable static-HTML dashboard that reports the current state of your repos — starting with `desireepaya/aws-security-baseline` and expandable via a hand-configured list. Regenerated on a GitHub Actions cron and published to public GitHub Pages.

**Phase 1 (this plan)**: pending changes only — open PRs and CI conclusions. Live public URL, end-to-end.

**Phase 2 (deferred)**: Terraform infra health (provider/module version lag from `.terraform.lock.hcl`).

The project lives in a **new repo** at `/Users/desiree/dev/repo-status-dashboard`, GitHub slug `desireepaya/repo-status-dashboard` (settled).

**Why this is worth building** (note for later readers, since with 1 repo/1 contributor much of this overlaps with Dependabot + native GH UI):
- The repo count will grow — aggregation across N repos is where the dashboard earns its keep over GH's per-repo UI.
- Portfolio value is high. A live public URL tied to the AWS security baseline work is a concrete, demonstrable artifact.
- Treat this as one build target, not a maintenance chore: the pipeline (Python + Jinja + GHA + Pages) is itself part of the story.

## Repo layout (Phase 1)

```
repo-status-dashboard/
├── pyproject.toml
├── README.md
├── config/
│   └── repos.yaml                  # hand-configured target repos
├── src/repo_status/
│   ├── __init__.py
│   ├── cli.py                      # `repo-status generate` entrypoint
│   ├── config.py                   # loads/validates repos.yaml
│   ├── models.py                   # dataclasses (RepoReport, PRSummary, …)
│   ├── collectors/
│   │   └── github.py               # PRs + CI check-runs via GH REST API
│   └── render.py                   # Jinja2 → dist/index.html
├── templates/
│   ├── index.html.j2
│   └── partials/*.j2
├── static/                         # single CSS file, no framework
└── .github/workflows/
    └── build-dashboard.yml         # cron + Pages deploy
```

Phase 2 adds `collectors/terraform.py`, a `tests/` dir with lock-file fixtures, and extends the config schema.

## Config format (`config/repos.yaml`)

```yaml
repos:
  - slug: desireepaya/aws-security-baseline
    display_name: AWS Security Baseline
```

Adding a new repo is a pure-config change — no code edits. Phase 2 will add an optional `terraform_stacks:` list under each repo.

## GitHub collector (`collectors/github.py`)

One authenticated call chain per configured repo:
- Open PRs: number, title, author, draft flag, `mergeable_state`, requested reviewers, review decision.
- For each PR: latest commit's check-runs summary (pass / fail / pending count).
- Uses `GITHUB_TOKEN` in GHA; a local PAT env var (`GH_TOKEN`) for dev.
- Prefer plain `httpx` calls over `PyGithub` to keep the dependency surface small and responses easy to stub in local dev.

## Rendering

- Single `index.html`. Summary strip at the top: total repos, total open PRs, total failing checks. One card per repo below.
- Jinja2 templates + one small stylesheet. No JS framework.
- Footer: `Generated: <UTC timestamp>` so staleness is obvious.
- Output directory: `dist/`. Emit `dist/index.html` plus copied `static/` assets.
- Include an "Infra health — coming soon" placeholder section on each card so the phase-2 slot is visible.

## GitHub Actions workflow (`.github/workflows/build-dashboard.yml`)

- Triggers: `schedule: cron: '0 15 * * *'` (15:00 UTC daily), `workflow_dispatch`, and `push` to `main` (so a `repos.yaml` edit rebuilds the site immediately rather than waiting for the next cron).
- Uses the modern Pages flow: `actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages`.
- Steps:
  1. Checkout dashboard repo.
  2. Install `uv`, sync deps.
  3. Run `uv run repo-status generate --config config/repos.yaml --out dist/`.
  4. Upload `dist/` as Pages artifact and deploy.
- Auth: `permissions: { contents: read, id-token: write, pages: write }`. `GITHUB_TOKEN` is sufficient for public target repos. No cloning of target repos in Phase 1 — the GitHub REST API covers all needed data.
- Enable Pages in repo settings with source = "GitHub Actions" (one-time manual step).

## Local dev

- `uv sync`
- `GH_TOKEN=$(gh auth token) uv run repo-status generate --config config/repos.yaml --out dist/` — reuses the existing `gh` CLI login, so there's no PAT to create or store.
- Optional `--serve` flag: run `python -m http.server` in `dist/` for browser preview.

## Files to reference

- `/Users/desiree/dev/aws-security-baseline/README.md` — tonal reference for the dashboard's own README (Phase 1 / Phase 2 framing, honest scoping notes).

## Explicit non-goals (Phase 1)

- No Terraform infra health — deferred to Phase 2 (planned, not dropped).
- No `terraform plan` / drift detection (later phase; needs AWS OIDC role).
- No security-posture reporting (secrets scan, CVEs) — dropped from scope.
- No local git hygiene (uncommitted / unpushed) — GHA cron has no view of your laptop.
- No auth on the artifact — Pages is public. Only surface data safe to publish (PR titles from a public repo are).

## Phasing

1. **Phase 1 — MVP + Ship**: repo skeleton, GitHub collector, Jinja render, local CLI, GHA cron, Pages deploy. Live public URL. Monitors just `aws-security-baseline`. PR/CI data only. **This is where Phase 1 ends — you should have a working live URL.**
2. **Phase 2 — Terraform metadata collector**: add `collectors/terraform.py`, `.terraform.lock.hcl` parsing, registry version-lag comparison, fixture tests, extend config schema with `terraform_stacks`.
3. **Extend**: add more repos to `repos.yaml`.
4. **Later**: drift detection via real `terraform plan` (needs AWS OIDC role).

## Verification (Phase 1)

- Local: `GH_TOKEN=$(gh auth token) uv run repo-status generate --config config/repos.yaml --out dist/` produces `dist/index.html`; open in browser; confirm open-PR count matches `gh pr list -R desireepaya/aws-security-baseline`.
- CI: manually dispatch `build-dashboard.yml`, confirm the run succeeds and Pages deploys.
- End-to-end: visit `https://desireepaya.github.io/repo-status-dashboard/`, confirm the page renders and the "Generated:" timestamp is recent.

## Settled decisions

- **GitHub repo name**: `repo-status-dashboard` (matches the local directory; no shorter alias).
- **"Commits since last tag"**: dropped from Phase 1 — no tags in use yet, so the surrogate would report nothing meaningful. Phase 1 surfaces PR + CI data only. Revisit if/when releases get tagged.
- **No dedicated token for GitHub Actions** — use the built-in `GITHUB_TOKEN`. Public repo data is readable by any authenticated token, so the dashboard repo's own `GITHUB_TOKEN` can read PRs and check-runs from the target repos; Pages deploy is covered by the `permissions:` block. A PAT would be a *downgrade*: long-lived, stored as a secret, manually rotated, broader scope than needed, on a public-facing project. `GITHUB_TOKEN` is minted per job and expires with it.
  - Rate limit is a non-issue: cost is ~`1 + (open PRs)` requests per target repo against a 1,000 req/hr per-repo ceiling, on a daily cron.
  - **Trigger to revisit: the first private repo added to `repos.yaml`.** `GITHUB_TOKEN` cannot read a private repo outside its own — a hard boundary, not a permissions tweak. At that point use a fine-grained PAT (read-only Pull requests + Checks + Metadata, selected repos, with an expiry) as a repo secret, or a GitHub App installation token for short-lived credentials. The collector needs no change either way — it reads whatever token is in the env var.
