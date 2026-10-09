# 1. Monorepo of projects with contract-based interaction

- **Status:** accepted
- **Date:** 2026-10-09

## Context

This repository will hold many AI agentic workflow projects, some of which need to exchange data. Without rules, projects start importing each other's internals and become impossible to change independently.

## Decision

- One folder per project under `projects/`, created from `templates/project/`.
- Each project declares its owner, status, dependencies and exposed contracts in `project.toml`.
- Projects interact only through versioned files in the provider's `contracts/` folder.
- Reusable, project-neutral pieces live in `shared/`, which never depends on a project.
- `scripts/validate.py` enforces these rules locally and in CI, using only the Python standard library.

## Consequences

- Projects can be added, changed or retired independently.
- Cross-project links are explicit and visible in the README index.
- Exposing data to another project takes a small amount of ceremony (a schema file and two manifest entries).
