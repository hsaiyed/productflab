# AgentGTM

AI agentic workflows for go-to-market work.

## Workflows

| Workflow | What it does |
| --- | --- |
| [bde-prospecting](workflows/bde-prospecting/) | Daily LinkedIn research tasks for BDEs, nightly checks, and ranked invite lists with drafted notes for founders |

Startup playbooks shared by all workflows are in [playbooks/](playbooks/).

## Interfaces

- **Depends on:** none
- **Exposes:** `contracts/prospect.v1.schema.json`, one researched prospect with check result and outreach status

See `project.toml` for the authoritative list.

## Environment variables

| Variable | Used by | Purpose |
| --- | --- | --- |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | bde-prospecting | Google Sheets access |
| `ANTHROPIC_API_KEY` | bde-prospecting (optional) | Claude for unclear titles and connection notes |
| `AGENTGTM_MODEL` | bde-prospecting (optional) | Claude model id |
| `PHOENIX_COLLECTOR_ENDPOINT` | bde-prospecting (optional) | Arize Phoenix tracing |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | bde-prospecting (email channel) | Outgoing mail |

## Layout

| Folder | What goes here |
| --- | --- |
| `workflows/` | End-to-end workflows, one folder per workflow |
| `agents/` | Agent definitions used by this project |
| `prompts/` | Prompt templates used by this project |
| `tools/` | Tools and integrations this project's agents call |
| `contracts/` | Public schemas other projects may rely on (list them in `exposes`) |
| `playbooks/` | One file per startup: personas, territories, exclusions |
| `docs/` | Design notes for this project |
| `tests/` | Tests and evals |
