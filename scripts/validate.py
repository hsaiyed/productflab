#!/usr/bin/env python3
"""Check the repo's structural rules. Runs in CI; run it locally before pushing.

Usage:
    python3 scripts/validate.py          # report problems, exit 1 if any
    python3 scripts/validate.py --fix    # also regenerate the project index in README.md

Rules:
  1. Every folder in projects/ has a valid project.toml whose name matches the folder.
  2. Project names are unique ignoring case.
  3. depends_on names existing projects, not itself, with no dependency cycles.
  4. Every file listed in exposes exists under that project's contracts/.
  5. A project references another project's files only through projects/<Dep>/contracts/<file>,
     where <Dep> is in its depends_on and <file> is in <Dep>'s exposes.
  6. shared/ never references projects/.
  7. The project index in README.md matches the manifests.
"""

import re
import sys
import tomllib

from repo import (
    NAME_RE,
    README,
    ROOT,
    STATUSES,
    load_manifest,
    project_dirs,
    render_index,
    replace_index,
)

REF_RE = re.compile(r"projects/([A-Za-z][A-Za-z0-9-]*)/([^\s\"'`)\]>,;]*)")
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".ico", ".woff", ".woff2"}
SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".git"}


def text_files(directory):
    for path in directory.rglob("*"):
        if path.is_file() and path.suffix.lower() not in SKIP_SUFFIXES and not SKIP_DIRS & set(path.parts):
            try:
                yield path, path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue


def find_cycle(graph):
    state = {}  # node -> "visiting" | "done"

    def visit(node, stack):
        state[node] = "visiting"
        for dep in graph.get(node, []):
            if state.get(dep) == "visiting":
                return stack[stack.index(dep):] + [dep]
            if dep not in state:
                cycle = visit(dep, stack + [dep])
                if cycle:
                    return cycle
        state[node] = "done"
        return None

    for node in sorted(graph):
        if node not in state:
            cycle = visit(node, [node])
            if cycle:
                return cycle
    return None


def main():
    fix = "--fix" in sys.argv[1:]
    errors = []
    warnings = []
    manifests = {}

    # Rules 1 and 2: manifests.
    seen = {}
    for pdir in project_dirs():
        name = pdir.name
        if name.lower() in seen:
            errors.append(f"projects/{name}: name clashes with projects/{seen[name.lower()]} (case-insensitive)")
        seen[name.lower()] = name
        if not NAME_RE.match(name):
            errors.append(f"projects/{name}: invalid folder name; use letters, digits and hyphens")
        if not (pdir / "project.toml").is_file():
            errors.append(f"projects/{name}: missing project.toml (create projects with scripts/new_project.py)")
            continue
        try:
            m = load_manifest(pdir)
        except tomllib.TOMLDecodeError as e:
            errors.append(f"projects/{name}/project.toml: invalid TOML: {e}")
            continue
        proj = m.get("project", {})
        iface = m.get("interfaces", {})
        if proj.get("name") != name:
            errors.append(f"projects/{name}/project.toml: [project].name is {proj.get('name')!r}, expected {name!r}")
        for field in ("description", "owner"):
            if not isinstance(proj.get(field), str) or not proj[field].strip() or "{{" in proj[field]:
                errors.append(f"projects/{name}/project.toml: [project].{field} must be set")
        if proj.get("status") not in STATUSES:
            errors.append(f"projects/{name}/project.toml: [project].status must be one of {sorted(STATUSES)}")
        for field in ("depends_on", "exposes"):
            value = iface.get(field, [])
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                errors.append(f"projects/{name}/project.toml: [interfaces].{field} must be a list of strings")
                iface[field] = []
        if not (pdir / "README.md").is_file():
            errors.append(f"projects/{name}: missing README.md")
        m.setdefault("interfaces", iface)
        manifests[name] = m

    # Rule 3: dependencies.
    graph = {}
    for name, m in manifests.items():
        deps = m["interfaces"].get("depends_on", [])
        graph[name] = [d for d in deps if d in manifests]
        for dep in deps:
            if dep == name:
                errors.append(f"projects/{name}: depends on itself")
            elif dep not in manifests:
                errors.append(f"projects/{name}: depends_on {dep!r}, which is not a project")
            elif manifests[dep]["project"].get("status") == "deprecated":
                warnings.append(f"projects/{name}: depends on deprecated project {dep}")
    cycle = find_cycle({n: [d for d in ds if d != n] for n, ds in graph.items()})
    if cycle:
        errors.append("dependency cycle: " + " -> ".join(cycle))

    # Rule 4: exposed contracts exist.
    for name, m in manifests.items():
        for contract in m["interfaces"].get("exposes", []):
            path = ROOT / "projects" / name / "contracts" / contract
            if not path.is_file():
                errors.append(f"projects/{name}: exposes {contract!r}, but contracts/{contract} does not exist")

    # Rule 5: cross-project references.
    for name, m in manifests.items():
        deps = set(m["interfaces"].get("depends_on", []))
        for path, text in text_files(ROOT / "projects" / name):
            rel = path.relative_to(ROOT)
            for target, rest in REF_RE.findall(text):
                if target == name:
                    continue
                where = f"{rel}: references projects/{target}/{rest}"
                if target not in manifests:
                    errors.append(f"{where}, which is not a project")
                elif target not in deps:
                    errors.append(f"{where}, but {target} is not in depends_on")
                elif not rest.startswith("contracts/"):
                    errors.append(f"{where}; only projects/{target}/contracts/ may be used by other projects")
                elif rest.removeprefix("contracts/") not in manifests[target]["interfaces"].get("exposes", []):
                    errors.append(f"{where}, which {target} does not list in exposes")

    # Rule 6: shared/ is independent of projects.
    shared = ROOT / "shared"
    if shared.is_dir():
        for path, text in text_files(shared):
            for target, rest in REF_RE.findall(text):
                errors.append(f"{path.relative_to(ROOT)}: shared code must not reference projects/{target}/{rest}")

    # Rule 7: README index.
    readme = README.read_text()
    try:
        updated = replace_index(readme, render_index(manifests))
    except ValueError as e:
        errors.append(str(e))
    else:
        if updated != readme:
            if fix:
                README.write_text(updated)
                print("Updated the project index in README.md.")
            else:
                errors.append("README.md project index is out of date; run python3 scripts/validate.py --fix")

    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    if errors:
        print(f"\n{len(errors)} problem(s) found.")
        sys.exit(1)
    print(f"OK: {len(manifests)} project(s) checked.")


if __name__ == "__main__":
    main()
