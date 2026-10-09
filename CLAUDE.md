# CLAUDE.md

This repository stores AI agentic workflow projects, one top-level folder per project (e.g. `AgentGTM/`).

- Each project has its own `README.md` and the layout `workflows/`, `agents/`, `prompts/`, `tools/`, `docs/`.
- Put each workflow in its own folder under the project's `workflows/` with a `README.md` describing its goal, inputs, outputs, and steps.
- Shared agent definitions go in `agents/`, reusable prompts in `prompts/`, callable tools in `tools/`.
- When adding a project, list it in the root `README.md`.
- Never commit API keys or other secrets; use environment variables and document which ones a workflow needs.
