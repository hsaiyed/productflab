# Architecture

## Goals

- Add new agentic workflow projects without touching existing ones.
- Let projects work together without becoming tangled.
- Make the rules machine-checked, so the structure holds up as the repo grows.

## Three layers

| Layer | Path | May depend on |
| --- | --- | --- |
| Projects | `projects/<Name>/` | `shared/`, and other projects' exposed contracts |
| Shared | `shared/` | nothing in `projects/` |
| Tooling | `templates/`, `scripts/`, `.github/` | — |

## The project manifest

Every project has a `project.toml`:

```toml
[project]
name = "AgentGTM"            # matches the folder name
description = "..."
owner = "hsaiyed"
status = "active"            # experimental | active | deprecated

[interfaces]
depends_on = []              # projects whose contracts this one uses
exposes = []                 # files in contracts/ that other projects may use
```

## How projects interact

Projects interact through **contracts**, never through each other's internals.

A contract is a file in the providing project's `contracts/` folder that describes data passed between projects: typically a JSON Schema for a record (a lead, an account, a ticket) or for an event one workflow emits and another consumes.

Rules, enforced by `scripts/validate.py`:

1. The provider lists the file in `exposes`.
2. The consumer lists the provider in `depends_on`.
3. The consumer references only `projects/<Provider>/contracts/<file>`.
4. Dependencies form no cycles. If two projects need each other, move the shared piece into `shared/` or into a new project both depend on.
5. `shared/` never references `projects/`.

How data actually moves at runtime (files, a queue, an HTTP call, one workflow invoking another) is up to the projects; the contract fixes the shape of what moves.

### Versioning contracts

Contracts are public APIs. Put the version in the file name, e.g. `lead.v1.schema.json`.

- Adding optional fields is fine in place.
- Removing or renaming fields, or changing types, is a breaking change: add `lead.v2.schema.json`, expose both, move consumers over, then remove v1.

## When to use shared/ vs a contract

- **`shared/`**: reusable building blocks with no project-specific meaning: a generic web-search tool, a summarization prompt, a common `company.schema.json`.
- **A contract**: data that one project owns and others consume, e.g. AgentGTM's qualified-lead record.

Promote something to `shared/` once a second project needs it; don't copy it.

## Project lifecycle

`experimental` → `active` → `deprecated`. Projects depending on a deprecated project get a validator warning. Delete a deprecated project once nothing depends on it.

## Decisions

Significant structural decisions are recorded in `docs/adr/`. Copy the format of `0001-monorepo-structure.md`.
