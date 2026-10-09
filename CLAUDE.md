# CLAUDE.md

This repository stores AI agentic workflows. See `README.md` for the folder layout.

- Put each workflow in its own folder under `workflows/` with a `README.md` describing its goal, inputs, outputs, and steps.
- Shared agent definitions go in `agents/`, reusable prompts in `prompts/`, callable tools in `tools/`.
- Never commit API keys or other secrets; use environment variables and document which ones a workflow needs.
