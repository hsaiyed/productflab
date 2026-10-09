#!/usr/bin/env python3
"""Create a new project from templates/project and add it to the root README index.

Usage:
    python3 scripts/new_project.py <Name> "<one-line description>" [--owner <owner>]
"""

import argparse
import shutil
import sys

from repo import NAME_RE, PROJECTS_DIR, README, ROOT, load_manifest, project_dirs, render_index, replace_index

TEMPLATE_DIR = ROOT / "templates" / "project"
FILLED = ("project.toml", "README.md")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("name", help="Project name, e.g. AgentSupport (letters, digits, hyphens)")
    parser.add_argument("description", help="One-line description of the project")
    parser.add_argument("--owner", default="hsaiyed")
    args = parser.parse_args()

    if not NAME_RE.match(args.name):
        sys.exit(f"error: invalid project name {args.name!r}; use letters, digits and hyphens, starting with a letter")
    existing = {p.name.lower() for p in project_dirs()}
    if args.name.lower() in existing:
        sys.exit(f"error: a project named {args.name!r} already exists (names are case-insensitive)")
    if '"' in args.description or "|" in args.description:
        sys.exit('error: description must not contain " or |')

    target = PROJECTS_DIR / args.name
    shutil.copytree(TEMPLATE_DIR, target)
    for filename in FILLED:
        path = target / filename
        text = path.read_text()
        text = text.replace("{{name}}", args.name).replace("{{description}}", args.description)
        path.write_text(text.replace("{{owner}}", args.owner))

    manifests = {p.name: load_manifest(p) for p in project_dirs()}
    README.write_text(replace_index(README.read_text(), render_index(manifests)))

    print(f"Created projects/{args.name}/ and added it to README.md.")
    print("Next: edit its project.toml and README.md, then run python3 scripts/validate.py")


if __name__ == "__main__":
    main()
