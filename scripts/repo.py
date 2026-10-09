"""Shared helpers for the repo scripts: load project manifests and render the project index."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROJECTS_DIR = ROOT / "projects"
README = ROOT / "README.md"

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*$")
STATUSES = {"experimental", "active", "deprecated"}
INDEX_START = "<!-- projects:start -->"
INDEX_END = "<!-- projects:end -->"


def project_dirs():
    if not PROJECTS_DIR.is_dir():
        return []
    return sorted(p for p in PROJECTS_DIR.iterdir() if p.is_dir() and not p.name.startswith("."))


def load_manifest(project_dir):
    with open(project_dir / "project.toml", "rb") as f:
        return tomllib.load(f)


def render_index(manifests):
    """Render the project table for the root README from {name: manifest}."""
    lines = [
        INDEX_START,
        "| Project | Status | Description | Depends on |",
        "| --- | --- | --- | --- |",
    ]
    for name in sorted(manifests, key=str.lower):
        m = manifests[name]
        proj = m.get("project", {})
        deps = m.get("interfaces", {}).get("depends_on", [])
        lines.append(
            f"| [{name}](projects/{name}/) | {proj.get('status', '')} | "
            f"{proj.get('description', '')} | {', '.join(deps) or '—'} |"
        )
    lines.append(INDEX_END)
    return "\n".join(lines)


def replace_index(readme_text, index):
    pattern = re.compile(re.escape(INDEX_START) + r".*?" + re.escape(INDEX_END), re.S)
    if not pattern.search(readme_text):
        raise ValueError(f"README.md is missing the {INDEX_START} / {INDEX_END} markers")
    return pattern.sub(lambda _: index, readme_text)
