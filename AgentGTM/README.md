# AgentGTM

AI agentic workflows for go-to-market work.

## Layout

| Folder | What goes here |
| --- | --- |
| `workflows/` | End-to-end agentic workflows, one folder per workflow |
| `agents/` | Agent definitions: role, instructions, tools, model settings |
| `prompts/` | Reusable prompt templates shared across agents and workflows |
| `tools/` | Tools and integrations agents can call (scripts, MCP servers, API wrappers) |
| `docs/` | Design notes, decisions, and how-tos |

## Adding a workflow

Create `workflows/<workflow-name>/` with:

- `README.md` — goal, inputs, outputs, and the steps or agents involved
- the workflow code or config
- an `examples/` folder with sample inputs and expected outputs, if useful

Read API keys from environment variables and list the ones a workflow needs in its README.
