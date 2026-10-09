# BDE prospecting

Turns four BDEs in India doing manual LinkedIn research into a steady, checked flow of US prospects for each startup's founder, without automating LinkedIn.

**Goal:** more qualified first conversations per founder per week, which is what moves a seed startup from $0–500K toward $1–4M ARR.

## How a day works

| Time (IST) | Time (US Eastern) | Step | Command |
| --- | --- | --- | --- |
| 09:30 | 00:00 | Each BDE gets today's task (startup, persona, territory, search string, target) plus yesterday's results | `plan` |
| 10:00–19:00 | | BDEs research on LinkedIn and add rows to the shared Google Sheet | (people) |
| 20:00 | 10:30 | Every new row is checked; unclear ones go to you | `check` |
| 20:15 | 10:45 | Each founder gets 15 ranked invites with a drafted note, and sends them in ~10 minutes | `founder-batch` |
| Monday 09:00 | | You get the weekly report with suggestions | `weekly-report` |

The full design (users, boundaries, evals, launch plan) is in [docs/design.md](docs/design.md). The guide to send BDEs is [docs/bde-guide.md](docs/bde-guide.md).

## Inputs

- `../../playbooks/<startup>.toml`: what each startup sells, personas, territory weights, exclusions
- `config/bdes.toml`: BDEs, their LinkedIn plan, assigned startups, daily target, message channel
- `config/territories.toml`: US territories and the states and metros in each
- The Google Sheet: `Prospects`, `Tasks` and `DoNotContact` tabs

## Outputs

- Updated sheet: check results, scores, notes, status
- Messages (always written to `outbox/<date>/`, delivered with `--send`): BDE tasks, founder invite lists, rows needing review, weekly report
- Traces in Arize Phoenix, if configured

## Try it (no accounts needed)

```sh
cd projects/AgentGTM/workflows/bde-prospecting
pip install -e '.[dev]'
python -m bde_prospecting demo --no-llm     # full day on the example sheet
pytest                                       # 35 tests
python tests/evals/eval_persona.py           # persona-matching eval
```

## Set up for real

1. **Google Sheet.** Create an empty Google Sheet. In Google Cloud, create a service account, download its JSON key, and share the sheet with the service account's email as an editor. Then:
   ```sh
   export GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/key.json
   python -m bde_prospecting setup --store sheets:<spreadsheet-id>
   ```
   This creates the tabs, headers and dropdowns, and warns anyone editing the agent's columns. Share the sheet with the BDEs and founders.
2. **Playbooks.** Review each `playbooks/*.toml` with its founder: personas, territories, `exclude_companies` (customers and competitors), founder name and channel. Set `confirmed = true`.
3. **Roster.** Fill in names and channels in `config/bdes.toml`.
4. **Claude (optional but recommended).** Set `ANTHROPIC_API_KEY`. Claude decides unclear title matches and writes connection notes. Without it, unclear titles go to you and notes use a template.
5. **Phoenix (optional).** Run Phoenix (`pip install arize-phoenix && phoenix serve`), `pip install -e '.[tracing]'`, and set `PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006`.
6. **Run a dry week.** Run the daily commands without `--send` and read `outbox/`. Add `--send` once the messages look right.
7. **Schedule it.** `.github/workflows/agentgtm-bde-prospecting.yml` runs the steps on GitHub Actions. Add the secrets listed below and set the repository variable `AGENTGTM_BDE_ENABLED` to `true`.

## Commands

```sh
python -m bde_prospecting <command> --store sheets:<id> [--date YYYY-MM-DD] [--send] [--no-llm]
```

| Command | What it does |
| --- | --- |
| `setup` | Create tabs, headers, dropdowns |
| `plan` | Pick each BDE's focus for the day and send the task (runs once per day; re-running does nothing) |
| `check` | Check unchecked rows; send rows needing review to you |
| `founder-batch` | Queue each founder's top invites with notes (`--startup daxa` for one) |
| `weekly-report` | Report on the previous 7 days |
| `demo` | Run a full day on `examples/demo-sheet` in a temp folder |

## Environment variables

| Variable | Needed for | Purpose |
| --- | --- | --- |
| `GOOGLE_SERVICE_ACCOUNT_FILE` | `sheets:` store | Path to the service account JSON key |
| `ANTHROPIC_API_KEY` | optional | Claude for unclear titles and notes |
| `AGENTGTM_MODEL` | optional | Claude model id (default `claude-opus-5-5`) |
| `PHOENIX_COLLECTOR_ENDPOINT` | optional | Arize Phoenix URL for tracing |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | `email` channel | Outgoing mail |
| *(name you choose)* | `slack` channel | Slack incoming-webhook URL; put the variable's name in `contact` |

## Safety rules built into the code

- Nothing touches LinkedIn. Founders send every invite themselves.
- Messages only go to people in the config (BDEs, founders, you), never to prospects.
- Nothing is delivered without `--send`; everything is written to `outbox/` first.
- Claude only sees a title, company, persona and the BDE's note. Text typed by BDEs is passed as data, not instructions.
- Every note passes guardrails (length, name, no links or placeholders) or is replaced by the template.
- The agent never edits playbooks or assignments. The weekly report suggests changes for you to make.
- The sheet stores only work details. No personal emails or phone numbers.
