"""Static dashboard reporting pending changes across configured GitHub repos."""

from pathlib import Path

__version__ = "0.1.0"

# Templates and static assets live at the repo root, not inside the package,
# so resolve them relative to the project root. src/repo_status/__init__.py
# -> parents[2] is the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATES_DIR = PROJECT_ROOT / "templates"
DEFAULT_STATIC_DIR = PROJECT_ROOT / "static"
