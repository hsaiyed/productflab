# productflab

A monorepo of AI agentic workflow projects. Each project is self-contained under `projects/`, can reuse building blocks from `shared/`, and can work with other projects through declared contracts.

## Projects

<!-- projects:start -->
| Project | Status | Description | Depends on |
| --- | --- | --- | --- |
| [AgentGTM](projects/AgentGTM/) | active | AI agentic workflows for go-to-market work. | — |
<!-- projects:end -->

This table is generated from each project's `project.toml`. Don't edit it by hand; run `python3 scripts/validate.py --fix`.

## Layout

```
productflab/
├── projects/            one folder per project
│   └── <Name>/
│       ├── project.toml     manifest: name, owner, status, depends_on, exposes
│       ├── README.md
│       ├── workflows/       one folder per workflow
│       ├── agents/          agent definitions
│       ├── prompts/         prompt templates
│       ├── tools/           tools and integrations
│       ├── contracts/       public schemas other projects may use
│       ├── docs/
│       └── tests/
├── shared/              building blocks any project may use (never depends on a project)
│   ├── agents/  prompts/  tools/  schemas/
├── templates/project/   template that new projects are copied from
├── scripts/             new_project.py, validate.py
└── docs/                repo-wide architecture notes and decision records (docs/adr/)
```

## Common tasks

**Create a project**

```sh
python3 scripts/new_project.py AgentSupport "Agents that triage and answer support tickets"
```

**Let one project use another.** Say AgentSupport needs leads from AgentGTM:

1. AgentGTM adds a schema such as `contracts/lead.v1.schema.json` and lists it in `exposes`.
2. AgentSupport adds `"AgentGTM"` to `depends_on` and refers only to `projects/AgentGTM/contracts/lead.v1.schema.json`.

See [docs/architecture.md](docs/architecture.md) for the full rules.

**Check the structure** (also runs in CI on every push and pull request; needs Python 3.11+)

```sh
python3 scripts/validate.py
```

## Secrets

Never commit API keys. Copy `.env.example` to `.env` (ignored by git) and document every variable a workflow needs in its project README.
