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
| Schedule, 09:30 IST | `plan`: daily tasks |
| Schedule, 20:00 IST | `check` then `founder-batch` |
| Schedule, Monday | `weekly-report` |
| Manual | Any command, any date (`--date`), e.g. to re-run after fixing the sheet |

## Agent loop and handoffs

```
           ┌──────────── weekly: report + suggestions ─────────────┐
           ▼                                                       │
 YOU ── edit playbooks ──► PLAN ──task──► BDE ──rows──► CHECK ──► FOUNDER BATCH ──► FOUNDER ──status──┘
 ▲                          (rules)                     (rules,    (rank, Claude      sends invites
 │                                                       Claude     drafts note,      from own LinkedIn
 └──────── rows needing review ◄──────────────────────── if unclear) guardrails)
```

Each arrow is a handoff with a defined format: the task message, the sheet row (contract: `contracts/prospect.v1.schema.json`), the founder's invite list, the review list, the report.

The loop learns through data, not by changing itself: acceptance rates feed the planner's weights automatically; anything bigger (a new persona, a territory change) is a suggestion you approve by editing a playbook.

**Where Claude is used, and why only there:**
- Deciding titles the rules can't (e.g. "Reliability Lead, Payments"). Rules handle ~98% of titles for free.
- Writing the connection note, which needs judgement about tone.

Everything else is deterministic code. That keeps cost low, behaviour predictable, and results testable.

## Uncertainty

| Situation | Behaviour |
| --- | --- |
| Title doesn't clearly match | Claude decides; if Claude is unsure, unavailable, or declines → `needs_review`, sent to you |
| Row has a fixable problem | `rejected` with the exact reason; BDE fixes it and clears `check_status` |
| Claude's note fails a guardrail | Template note instead; never an unchecked note |
| Too little history to judge a persona | Planner ignores performance until 10+ invites |
| Playbook not confirmed by founder | Flagged in every weekly report |

## Human boundaries

| Actor | Can | Cannot |
| --- | --- | --- |
| Agent | Assign tasks, check rows, rank, draft notes, report, suggest | Touch LinkedIn; message prospects; change playbooks, roster or assignments rules; deliver without `--send` |
| BDE | Research on their own LinkedIn; add and fix rows | Use founders' accounts; contact prospects; collect personal contact details |
| Founder | Send or skip invites; update status | — |
| You | Approve playbooks, resolve review rows, act on suggestions | — |

## Data plan

| Data | Where | Retention |
| --- | --- | --- |
| Prospects (work details only) | Google Sheet `Prospects` | Until `not_a_fit` or `do_not_contact`; then archive yearly |
| Daily tasks | Sheet `Tasks` | Kept, used for rotation |
| Do-not-contact | Sheet `DoNotContact` | Permanent |
| Messages sent | `outbox/` (not in git) | 90 days |
| Claude traces | Phoenix (self-hosted) | 30 days |
| Playbooks, config | This repo | Versioned |

Not collected: personal emails, phone numbers, home addresses, anything beyond what's on a public LinkedIn profile's headline. Opt-outs go on `DoNotContact` immediately.

## Evals

| Eval | How | Bar |
| --- | --- | --- |
| Persona matching | `tests/evals/eval_persona.py`: 50 human-labelled titles, rules (+ Claude with `--llm`) | ≥95% accuracy on decided titles, 0 wrongly accepted; runs in CI |
| Checker, planner, founder batch | 35 pytest tests incl. a full day on the demo sheet | All pass; runs in CI |
| Note guardrails | Every note checked before a founder sees it | 100% pass or template |
| Note quality (next) | Phoenix: LLM-as-judge on traced notes (specific, peer tone, no invented facts), spot-checked weekly by you | Set after 2 weeks of data |
| Business outcome | Weekly report: valid rate per BDE, invite acceptance per persona, meetings | Acceptance ≥30%; valid rate ≥80% |

Add every wrong call you find to `persona_titles.csv`; the eval set grows with real mistakes.

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
- **Phoenix:** every Claude call traced with latency, tokens and errors; one span per command.
- **Weekly report:** BDE valid rates, funnel per persona, founder backlog (invites not being sent), unconfirmed playbooks.
- **Watch for:** valid rate dropping for a BDE (retrain), backlog growing (founder bottleneck: reduce BDE hours), acceptance <15% (persona or note problem).

## Demo (10 minutes, for founders or investors)

1. `python -m bde_prospecting demo --no-llm` (or with `ANTHROPIC_API_KEY` for Claude notes).
2. Show the nightly check: a duplicate, a Sales Navigator link, a junior title, a competitor on the do-not-contact list, a person outside the territory, each caught with a reason.
3. Show a founder's invite list: ranked, with notes.
4. Show the next morning's BDE task: rotated focus, Google search for free accounts, and yesterday's feedback.
5. Show the weekly report funnel and suggestions.
6. With Phoenix running, open a trace of the Claude title decision.

## Cost

| Item | Cost |
| --- | --- |
| Google Sheets, GitHub Actions, Phoenix (self-hosted) | Free at this scale |
| Claude | Small: a few unclear titles a day plus ~60 short notes a day. Switch `AGENTGTM_MODEL` to a smaller model if the eval shows quality holds. |
| BDEs | The main cost |
