"""Command line: python -m bde_prospecting <command> --store <csv:dir | sheets:id>

The agent (needs ANTHROPIC_API_KEY):
  agent morning   09:30 IST  assign each BDE's task, with coaching
  agent evening   20:00 IST  check today's rows, queue founders' invites with notes
  agent weekly    Monday     analyse performance, report and propose changes
  agent ask --question "..."   answer your question from the data (read-only)

Fixed-rule fallback (no Claude): plan, check, founder-batch, weekly-report.
`run <mode>` uses the agent when Claude is configured and the fallback otherwise.

Nothing is delivered unless --send is given; without it messages are only written to the outbox.
"""

import argparse
import logging
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from . import checker, founder, llm, messages, notify, planner, sheet, tracing
from .config import WORKFLOW_DIR, ConfigError, load_config
from .store import open_store

DEFAULT_OUTBOX = WORKFLOW_DIR / "outbox"
DEMO_DATE = date(2026, 10, 12)  # the date of the example rows


def cmd_setup(args, cfg, store):
    store.setup(cfg)
    print("Sheet is set up: Prospects, Tasks and DoNotContact tabs with headers and dropdowns.")


def cmd_plan(args, cfg, store):
    rows, tasks = store.read_prospects(), store.read_tasks()
    plan = planner.plan_day(cfg, rows, tasks, args.date)
    if not plan:
        print(f"Nothing to plan: tasks for {args.date} already exist, or no BDEs are configured.")
        return
    prev_day = planner.yesterday(args.date)
    prev_tasks = {t["bde_id"]: t["task_id"] for t in tasks if t["date"] == prev_day}
    store.append_tasks(t.as_row() for t in plan)
    for task in plan:
        prev_rows = [r for r in rows if r["task_id"] and r["task_id"] == prev_tasks.get(task.bde_id)]
        feedback = checker.summarize_by_bde(prev_rows).get(task.bde_id)
        body = messages.task_message(task, cfg, feedback, args.sheet_url)
        bde = cfg.bdes[task.bde_id]
        result = notify.deliver(args.outbox, args.date.isoformat(), task.bde_id, f"Today's prospecting task ({task.task_id})", body, bde.channel, bde.contact, args.send)
        print(f"{task.bde_id}: {task.startup} / {task.persona} / {task.territory} (weight {task.weight:.2f}), {result}")


def cmd_check(args, cfg, store):
    rows = store.read_prospects()
    chk = checker.Checker(cfg, use_llm=False if args.no_llm else None)
    with tracing.span("check", rows=len(rows)):
        updates = chk.check(rows, store.read_do_not_contact(), args.date.isoformat())
    store.update_prospects(updates)
    checked = [dict(r, **updates[r["_row"]]) for r in rows if r["_row"] in updates]
    for bde_id, s in sorted(checker.summarize_by_bde(checked).items()):
        print(f"{bde_id}: {s['checked']} checked, {s[sheet.VALID]} valid, {s[sheet.REJECTED]} rejected, {s[sheet.NEEDS_REVIEW]} need review")
    print(f"Claude title checks used: {chk.llm_calls}")
    review = [r for r in checked if r["check_status"] == sheet.NEEDS_REVIEW]
    if review:
        body = "\n".join(
            [f"{len(review)} rows need your decision. Set `check_status` to `valid` or `rejected` in the sheet.", ""]
            + [f"- Row {r['_row']} ({r['bde_id']}): {r['first_name']} {r['last_name']}, {r['title']} at {r['company']}: {r['check_reasons']}" for r in review]
        )
        print(notify.deliver(args.outbox, args.date.isoformat(), "owner-review", "Rows needing review", body, cfg.owner.channel, cfg.owner.contact, args.send))


def cmd_founder_batch(args, cfg, store):
    rows, dnc = store.read_prospects(), store.read_do_not_contact()
    updates = {}
    for pb in sorted(cfg.playbooks.values(), key=lambda p: p.id):
        if args.startup and pb.id != args.startup:
            continue
        with tracing.span("founder_batch", startup=pb.id):
            picks = founder.pick_and_draft(cfg, pb, rows, use_llm=False if args.no_llm else None, dnc_rows=dnc)
        if not picks:
            print(f"{pb.id}: no new valid prospects")
            continue
        for row, note, _ in picks:
            updates[row["_row"]] = {"founder_note": note, "status": sheet.QUEUED, "status_updated": args.date.isoformat()}
        body = messages.founder_message(pb, [(r, n) for r, n, _ in picks], args.date.isoformat())
        result = notify.deliver(args.outbox, args.date.isoformat(), f"founder-{pb.id}", f"{pb.name}: today's LinkedIn invites", body, pb.founder_channel, pb.founder_contact, args.send)
        drafted = sum(1 for *_, src in picks if src == "claude")
        print(f"{pb.id}: {len(picks)} invites ({drafted} notes by Claude, {len(picks) - drafted} from template), {result}")
    store.update_prospects(updates)


def cmd_weekly_report(args, cfg, store):
    end = args.date - timedelta(days=1)
    start = end - timedelta(days=6)
    body = messages.weekly_report(cfg, store.read_prospects(), start.isoformat(), end.isoformat())
    print(notify.deliver(args.outbox, args.date.isoformat(), "weekly-report", "Weekly BDE prospecting report", body, cfg.owner.channel, cfg.owner.contact, args.send))


def cmd_agent(args, cfg, store):
    from .agent import run_agent
    from .tools import Toolbox

    if not llm.available():
        sys.exit("error: the agent needs ANTHROPIC_API_KEY (and the anthropic package); use `run` to fall back to fixed rules")
    if args.mode == "ask" and not args.question:
        sys.exit('error: agent ask needs --question "..."')
    toolbox = Toolbox(cfg, store, args.date, args.mode, send=args.send, outbox=args.outbox, sheet_url=args.sheet_url)
    result = run_agent(toolbox, question=args.question)
    print(result["summary"] or "(no summary)")
    print(f"\n{len(result['actions'])} actions, {len(result['escalations'])} escalations, "
          f"{result['usage']['turns']} turns, {result['usage']['input_tokens']} in / {result['usage']['output_tokens']} out tokens, {result['seconds']}s")
    if result["open_items"]:
        print("Still open: " + "; ".join(result["open_items"]))
    print(f"Transcript: {args.outbox / result['date'] / ('agent-' + args.mode + '-transcript.json')}")


FALLBACK = {"morning": ["plan"], "evening": ["check", "founder-batch"], "weekly": ["weekly-report"]}


def cmd_run(args, cfg, store):
    if llm.available() and not args.no_llm:
        return cmd_agent(args, cfg, store)
    if args.mode == "ask":
        sys.exit("error: ask needs Claude")
    print(f"Claude not configured: running the fixed-rule {args.mode} steps.")
    for name in FALLBACK[args.mode]:
        COMMANDS[name](args, cfg, store)


def cmd_demo(args, cfg, store):
    """Run the whole day on a copy of the example sheet. Writes nothing outside a temp folder."""
    tmp = Path(tempfile.mkdtemp(prefix="bde-demo-"))
    args.date = DEMO_DATE
    shutil.copytree(WORKFLOW_DIR / "examples" / "demo-sheet", tmp / "sheet")
    demo_store = open_store(f"csv:{tmp / 'sheet'}")
    args.outbox, args.send = tmp / "outbox", False
    for title, fn in (("1. Nightly check", cmd_check), ("2. Founder invite batch", cmd_founder_batch),
                      ("3. Next morning's BDE tasks", cmd_plan), ("4. Weekly report", cmd_weekly_report)):
        print(f"\n===== {title} =====")
        if fn is cmd_plan:
            args.date += timedelta(days=1)
        fn(args, cfg, demo_store)
    print(f"\nDemo output: {tmp}")
    for path in sorted((tmp / "outbox").rglob("*.md")):
        print(f"\n----- {path.relative_to(tmp)} -----\n{path.read_text()}")


COMMANDS = {
    "setup": cmd_setup,
    "plan": cmd_plan,
    "check": cmd_check,
    "founder-batch": cmd_founder_batch,
    "weekly-report": cmd_weekly_report,
    "demo": cmd_demo,
    "agent": cmd_agent,
    "run": cmd_run,
}


def main(argv=None):
    parser = argparse.ArgumentParser(prog="bde_prospecting", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("mode", nargs="?", choices=["morning", "evening", "weekly", "ask"], help="for agent and run")
    parser.add_argument("--question", help="for agent ask")
    parser.add_argument("--store", help="csv:<dir> or sheets:<spreadsheet id> (not needed for demo)")
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="run as if today were this date (YYYY-MM-DD)")
    parser.add_argument("--send", action="store_true", help="deliver messages on each person's channel, not just the outbox")
    parser.add_argument("--outbox", type=Path, default=DEFAULT_OUTBOX)
    parser.add_argument("--sheet-url", default="", help="link to include in BDE task messages")
    parser.add_argument("--startup", help="founder-batch for one startup only")
    parser.add_argument("--no-llm", action="store_true", help="don't call Claude (unclear titles go to review, notes use the template)")
    parser.add_argument("--config-dir", type=Path)
    parser.add_argument("--playbook-dir", type=Path)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        kwargs = {k: v for k, v in (("config_dir", args.config_dir), ("playbook_dir", args.playbook_dir)) if v}
        cfg = load_config(**kwargs)
    except ConfigError as e:
        sys.exit(f"error: {e}")
    if args.command != "demo" and not args.store:
        sys.exit("error: --store is required")
    if args.command in ("agent", "run") and not args.mode:
        sys.exit(f"error: {args.command} needs a mode: morning, evening, weekly or ask")
    tracing.setup()
    if args.store and args.store.startswith("csv:") and args.command != "setup" and not Path(args.store[4:]).is_dir():
        sys.exit(f"error: {args.store[4:]} doesn't exist; create it with `setup --store {args.store}`")
    store = open_store(args.store) if args.store else None
    with tracing.span(args.command, date=args.date.isoformat()):
        COMMANDS[args.command](args, cfg, store)


if __name__ == "__main__":
    main()
