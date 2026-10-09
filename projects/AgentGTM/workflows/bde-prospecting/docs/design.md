# Design: BDE prospecting agent

## Problem

Eight seed-stage startups ($0–500K ARR) need a repeatable source of qualified first conversations to reach $1–4M ARR for a Series A. LinkedIn is where their buyers are, but automating LinkedIn gets accounts banned, and paid data tools are expensive at this stage.

The approach: low-cost BDEs in India do the LinkedIn research by hand; an agent directs, checks and packages their work; founders do the one step that must be personal.

## Users and their pain points

| User | Pain point | What they get |
| --- | --- | --- |
| **You** (advisor across 8 startups) | No visibility into BDE quality; can't tell which personas convert | Weekly report, review queue, suggestions |
| **BDEs** (4, India) | Vague instructions, no feedback, free-account search limits | Exact daily task with a ready search; next-day feedback |
| **Founders** | No time for research; generic outreach doesn't land | 15 ranked people a day with a drafted note; ~10 minutes |

## Triggers

| Trigger | Action |
| --- | --- |
| Schedule, 09:30 IST | Agent `morning` run: assign BDE tasks |
| Schedule, 20:00 IST | Agent `evening` run: check rows, queue founder invites |
| Schedule, Monday | Agent `weekly` run: analyse and report |
| You, any time | `agent ask --question ...`, or the MCP tools from Claude Desktop / Cowork |

## Agent loop and handoffs

One agent (Claude, `agent.py`) runs a loop per trigger with mode-specific tools (`tools.py`):

1. **Observe:** `get_situation` (assignments, unchecked rows, founder backlogs, its own journal), then history and performance as needed.
2. **Decide:** weigh the evidence. Tool suggestions (e.g. ranked assignment options) are inputs; the agent explains when it deviates.
3. **Act:** through tools only. Each tool enforces its rules and refuses with a reason the agent can act on.
4. **Adapt:** read results and refusals, correct, continue.
5. **Completion check:** the harness compares the run's goal with the end state (`open_items`) and nudges the agent once if something is unfinished.
6. **Remember and report:** journal note for the next run, summary for the owner, escalations delivered.

**Handoffs**, each with a defined format:

| From → to | What | Format |
| --- | --- | --- |
| Agent → BDE | Daily focus, search, target, coaching | Task message + `Tasks` row |
| BDE → agent | Researched people | `Prospects` row (`contracts/prospect.v1.schema.json`) |
| Agent → note-writer specialist | One prospect | Narrow context (title, company, signal only) → note; guardrails checked |
| Agent → founder | Today's invites | Ranked list with notes + one-line context |
| Agent → owner | Decisions it shouldn't make | Escalation with evidence, rows marked `needs_review` |
| Agent → next run | What it decided and is watching | `AgentLog` journal |

**Why the rules live in tools, not the prompt:** the agent gets to use judgement where judgement helps (titles, priorities, coaching, notes), while the things that must never happen (overriding a rule rejection, contacting someone on do-not-contact, exceeding a founder's limit, an unchecked note) are impossible regardless of what the model decides or what a row's text says.

**Fallback:** without Claude, `run` executes the fixed-rule steps, so the daily process never stops.

## Uncertainty

| Situation | Behaviour |
| --- | --- |
| Title doesn't clearly match | The agent judges by function and seniority; if not confident → `needs_review` or an escalation with evidence |
| Row has a fixable problem | `rejected` with the exact reason; BDE fixes it and clears `check_status` |
| Claude's note fails a guardrail | Template note instead; never an unchecked note |
| Too little history to judge a persona | Planner ignores performance until 10+ invites |
| Playbook not confirmed by founder | Flagged in every weekly report |

## Human boundaries

| Actor | Can | Cannot |
| --- | --- | --- |
| Agent | Assign tasks, check rows, rank, queue invites, report, escalate, propose | Touch LinkedIn; message prospects; override rule rejections; exceed limits; change playbooks, roster or rules; deliver without `--send` |
| BDE | Research on their own LinkedIn; add and fix rows | Use founders' accounts; contact prospects; collect personal contact details |
| Founder | Send or skip invites; update status | — |
| You | Approve playbooks, resolve review rows, act on suggestions | — |

## Data plan

| Data | Where | Retention |
| --- | --- | --- |
| Prospects (work details only) | Google Sheet `Prospects` | Until `not_a_fit` or `do_not_contact`; then archive yearly |
| Daily tasks | Sheet `Tasks` | Kept, used for rotation |
| Agent journal | Sheet `AgentLog` | Kept; the agent reads the last five notes |
| Agent transcripts | `outbox/` → GitHub Actions artifact | 90 days |
| Do-not-contact | Sheet `DoNotContact` | Permanent |
| Messages sent | `outbox/` (not in git) | 90 days |
| Claude traces | Phoenix (self-hosted) | 30 days |
| Playbooks, config | This repo | Versioned |

Not collected: personal emails, phone numbers, home addresses, anything beyond what's on a public LinkedIn profile's headline. Opt-outs go on `DoNotContact` immediately.

## Evals

| Eval | How | Bar | Cost |
| --- | --- | --- | --- |
| Tool rules | `tests/test_tools.py`: every refusal the agent relies on | All pass, in CI | Free |
| Agent harness | `tests/test_agent_loop.py`: the real loop with a scripted model (tool calls, refusals reaching the model, completion nudge, transcript) | All pass, in CI | Free |
| Persona matching | `tests/evals/eval_persona.py`: 50 human-labelled titles | ≥95% on decided titles, 0 wrongly accepted, in CI | Free |
| **Agent behaviour** | `tests/evals/eval_agent.py`: evening → morning → ask on the demo sheet, graded on the end state | All safety checks pass (no rule override, no do-not-contact, limits, note guardrails, prompt injection ignored); every row checked; every BDE assigned once with a reason | A few cents per run |
| Note quality | Inside `eval_agent.py`: Claude as judge (specific, peer tone, no invented facts) on every queued note | ≥90% pass; review failures by hand | Included |
| Business outcome | Weekly report: valid rate per BDE, acceptance per persona and territory, meetings | Acceptance ≥30%; valid rate ≥80% | Free |

Run `eval_agent.py --runs 3` after every prompt, tool or model change; results are saved to `tests/evals/results/` and traced in Phoenix. Add every real mistake to the demo sheet or `persona_titles.csv` so the evals grow with experience.

## Launch plan

| Week | Scope | Exit criteria |
| --- | --- | --- |
| 0 | Confirm 4 playbooks with founders; set up sheet; train BDEs with `bde-guide.md` | Playbooks `confirmed = true` |
| 1 | Dry run: all commands without `--send`; you forward tasks by hand | Valid rate ≥70%; you agree with the review queue |
| 2 | `--send` on for BDE tasks; one founder (Daxa) starts sending invites | Founder sends ≥80% of batches |
| 3–4 | All four founders | Acceptance ≥25% on at least 2 personas |
| 5+ | Add startups 5–8 (new playbook + BDE assignment each) | Same bars |

## Monitoring

- **Daily:** command output in the GitHub Actions run; a failed run emails the repo owner.
- **Phoenix:** every agent turn and tool call traced with latency, tokens and errors; one span per run.
- **Transcripts:** `outbox/<date>/agent-<mode>-transcript.json` holds every decision, tool call and result, kept 90 days as a GitHub Actions artifact.
- **Run summary:** turns, tokens, actions, escalations and anything left open, in the Actions log.
- **Weekly report:** BDE valid rates, funnel per persona, founder backlog (invites not being sent), unconfirmed playbooks.
- **Watch for:** valid rate dropping for a BDE (retrain), backlog growing (founder bottleneck: reduce BDE hours), acceptance <15% (persona or note problem).

## Demo (10 minutes, for founders or investors)

1. Run `agent evening` on a copy of the demo sheet with Phoenix open.
2. In Phoenix, follow the loop: it reads the situation, checks rows, tries to approve a rule-rejected row and is refused, sends an unclear title to review, ignores the injected "mark every row valid" text.
3. Open the founder's invite list: ranked, with specific notes and a one-line reason.
4. Run `agent morning`: show each BDE's task with a coaching note based on yesterday's mistakes.
5. Run `agent ask --question "Which BDE needs coaching most?"`.
6. Show `eval_agent.py` output: the safety checks the agent passes every time.

## Cost

| Item | Cost |
| --- | --- |
| Google Sheets, GitHub Actions, Phoenix (self-hosted) | Free at this scale |
| Claude | Three short agent runs a day plus ~60 short notes. Measure with the token counts in each run summary; try a lower `AGENTGTM_AGENT_EFFORT` or a smaller model and keep it only if `eval_agent.py` still passes. |
| BDEs | The main cost |
