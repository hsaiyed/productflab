# CLAUDE.md

Monorepo of AI agentic workflow projects. Read `docs/architecture.md` before changing structure or adding cross-project links.

- Projects live in `projects/<Name>/`. Create new ones with `python3 scripts/new_project.py <Name> "<description>"`, never by hand.
- Each project's `project.toml` is the source of truth for its owner, status, `depends_on` and `exposes`.
- A project may use another project only through `projects/<Dep>/contracts/<file>`, with `<Dep>` in its `depends_on` and `<file>` in `<Dep>`'s `exposes`. Never reach into another project's workflows, agents, prompts or tools.
- Something two or more projects need goes in `shared/`. `shared/` must never reference `projects/`.
- Contracts are public APIs: never make a breaking change to an exposed file; add a new version (`lead.v2.schema.json`) and keep the old one until no project depends on it.
- Each workflow gets its own folder under the project's `workflows/` with a `README.md` covering goal, inputs, outputs and steps.
- Never commit API keys or other secrets. Use environment variables, add them to `.env.example`, and document them in the project README.
- Run `python3 scripts/validate.py` before committing; use `--fix` to regenerate the README project index.
