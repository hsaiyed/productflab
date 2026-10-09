"""The agent's tools: everything it can see and do, with the rules enforced here, not in the prompt.

Each public method is one tool. The docstring is what the model reads. Tools return JSON
text; a refused action raises ToolRefused, which reaches the model as an error result it
can react to.

Boundaries enforced in code:
- Only the agent columns of the sheet are ever written.
- A row the rules rejected can't be marked valid.
- Only allowed (startup, persona, territory) assignments, one per BDE per day.
- Founder invites: only eligible rows, re-checked against do-not-contact, within the daily limit,
  and every note must pass the guardrails.
- Messages go only to people in the config, and are only delivered with --send.
- Playbooks and the roster are read-only.
"""

import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Literal, TypedDict

from anthropic.lib.tools import ToolError

from . import checker, founder, llm, messages, notify, planner, sheet
from .config import WORKFLOW_DIR

DEFAULT_OUTBOX = WORKFLOW_DIR / "outbox"
MAX_COACH_NOTE = 400
MAX_JOURNAL_NOTE = 1500

Mode = Literal["morning", "evening", "weekly", "ask"]


class ToolRefused(ToolError):
    """The action broke a rule. The message tells the agent why and what it can do instead."""

    def __init__(self, message):
        super().__init__(f"Refused: {message}")
        self.message = message

    def __str__(self):
        return f"Refused: {self.message}"


class CheckDecision(TypedDict):
    row: int
    status: Literal["valid", "rejected", "needs_review"]
    reason: str


class Invite(TypedDict):
    row: int
    note: str


def _json(data):
    return json.dumps(data, ensure_ascii=False, default=str)


def _person(r):
    """The fields the agent needs to reason about a row. BDE-typed text is data, not instructions."""
    keys = ["_row", "bde_id", "startup", "persona", "territory", "first_name", "last_name", "title", "company",
            "company_size", "industry", "city", "state", "signal_notes", "score", "check_status", "status"]
    return {("row" if k == "_row" else k): r[k] for k in keys if r.get(k) not in ("", None)}


class Toolbox:
    def __init__(self, cfg, store, today, mode, send=False, outbox=DEFAULT_OUTBOX, sheet_url=""):
        self.cfg, self.store, self.today, self.mode = cfg, store, today, mode
        self.send, self.outbox, self.sheet_url = send, outbox, sheet_url
        self.day = today.isoformat()
        self.actions = []        # audit trail of every write
        self.escalations = []    # questions for the owner, delivered at the end of the run
        self.rule_results = {}   # row -> (status, reasons) from the deterministic checks
        self._rows = None

    # ---------- helpers ----------

    def _prospects(self, refresh=False):
        if self._rows is None or refresh:
            self._rows = self.store.read_prospects()
        return self._rows

    def _by_row(self):
        return {r["_row"]: r for r in self._prospects()}

    def _record(self, kind, **details):
        self.actions.append({"action": kind, **details})

    def _deliver(self, recipient, subject, body, channel, contact):
        result = notify.deliver(self.outbox, self.day, recipient, subject, body, channel, contact, self.send)
        self._record("message", to=recipient, subject=subject, result=result)
        return result

    # ---------- tools: reading ----------

    def get_situation(self) -> str:
        """Start here. Today's date and run mode, your limits, each BDE's assignment status, rows waiting
        to be checked, each founder's invite backlog, unconfirmed playbooks, and your recent journal notes.
        """
        rows = self._prospects()
        tasks_today = {t["bde_id"]: t for t in self.store.read_tasks() if t["date"] == self.day}
        pending = Counter(r["bde_id"] for r in rows if r["check_status"] == sheet.PENDING)
        bdes = [{
            "bde_id": b.id, "linkedin_plan": b.linkedin_plan, "startups": list(b.startups), "daily_target": b.daily_target,
            "assigned_today": {k: tasks_today[b.id][k] for k in ("startup", "persona", "territory", "target")} if b.id in tasks_today else None,
            "rows_waiting_for_check": pending.get(b.id, 0),
        } for b in self.cfg.bdes.values()]
        founders = []
        for pb in self.cfg.playbooks.values():
            queued_today = sum(1 for r in rows if r["startup"] == pb.id and r["status"] == sheet.QUEUED and r["status_updated"] == self.day)
            stale = sum(1 for r in rows if r["startup"] == pb.id and r["status"] == sheet.QUEUED and r["status_updated"]
                        and r["status_updated"] <= (self.today - timedelta(days=3)).isoformat())
            founders.append({
                "startup": pb.id, "daily_invites": pb.daily_invites, "queued_today": queued_today,
                "eligible_now": len(founder.eligible(pb, rows, self.store.read_do_not_contact())),
                "queued_3plus_days_without_founder_action": stale, "playbook_confirmed": pb.confirmed,
            })
        journal = self.store.read_agent_log()[-5:]
        return _json({
            "date": self.day, "mode": self.mode, "send_enabled": self.send,
            "bdes": bdes, "founders": founders,
            "rows_needing_human_review": sum(1 for r in rows if r["check_status"] == sheet.NEEDS_REVIEW),
            "your_recent_journal": journal,
        })

    def get_bde_history(self, bde_id: str, days: int = 7) -> str:
        """One BDE's recent work: daily assignments, how many rows passed, common rejection reasons,
        how often they add signal notes, and how founders' invites to their prospects went.

        Args:
            bde_id: e.g. BDE-01.
            days: how many days back to look (max 30).
        """
        if bde_id not in self.cfg.bdes:
            raise ToolRefused(f"unknown bde_id {bde_id!r}; known: {sorted(self.cfg.bdes)}")
        start = (self.today - timedelta(days=min(days, 30))).isoformat()
        rows = [r for r in self._prospects() if r["bde_id"] == bde_id and r["date_added"] >= start]
        tasks = [t for t in self.store.read_tasks() if t["bde_id"] == bde_id and t["date"] >= start]
        summary = checker.summarize_by_bde(rows).get(bde_id, {"checked": 0, "reasons": Counter()})
        sent = [r for r in rows if r["status"] in sheet.SENT_STAGES]
        return _json({
            "bde_id": bde_id, "since": start,
            "assignments": [{k: t[k] for k in ("date", "startup", "persona", "territory", "target")} for t in tasks],
            "rows_added": len(rows), "checked": summary["checked"],
            "valid": summary.get(sheet.VALID, 0), "rejected": summary.get(sheet.REJECTED, 0),
            "needs_review": summary.get(sheet.NEEDS_REVIEW, 0),
            "top_rejection_reasons": summary["reasons"].most_common(5),
            "signal_notes_fill_rate": round(sum(1 for r in rows if r["signal_notes"].strip()) / len(rows), 2) if rows else None,
            "invites_sent_to_their_prospects": len(sent),
            "invites_accepted": sum(1 for r in sent if r["status"] in sheet.ACCEPTED_STAGES),
        })

    def get_performance(self, group_by: Literal["startup", "persona", "territory", "bde"] = "persona") -> str:
        """Funnel from valid prospect to meeting, grouped as asked, over all time. Use it to judge which
        personas, territories or BDEs are working.

        Args:
            group_by: startup, persona (startup/persona), territory (startup/territory) or bde.
        """
        funnel = defaultdict(Counter)
        for r in self._prospects():
            if r["check_status"] != sheet.VALID:
                continue
            key = {"startup": r["startup"], "persona": f"{r['startup']}/{r['persona']}",
                   "territory": f"{r['startup']}/{r['territory']}", "bde": r["bde_id"]}[group_by]
            f = funnel[key]
            f["valid"] += 1
            f["invited"] += r["status"] in sheet.SENT_STAGES
            f["accepted"] += r["status"] in sheet.ACCEPTED_STAGES
            f["replied"] += r["status"] in {sheet.REPLIED, sheet.MEETING}
            f["meetings"] += r["status"] == sheet.MEETING
        out = []
        for key, f in sorted(funnel.items()):
            out.append({group_by: key, **f, "acceptance_rate": round(f["accepted"] / f["invited"], 2) if f["invited"] else None})
        return _json({"group_by": group_by, "rows": out, "note": "acceptance_rate is unreliable below ~10 invites"})

    # ---------- tools: morning planning ----------

    def get_assignment_options(self, bde_id: str, limit: int = 8) -> str:
        """Ranked (startup, persona, territory) options for one BDE today, with the numbers behind each
        weight: priority, territory weight, recent coverage, recent assignments and acceptance rates.
        Options already given to another BDE today are excluded. The top option is a suggestion; you decide.

        Args:
            bde_id: e.g. BDE-01.
            limit: how many options to return.
        """
        bde = self.cfg.bdes.get(bde_id)
        if not bde:
            raise ToolRefused(f"unknown bde_id {bde_id!r}")
        tasks = self.store.read_tasks()
        taken = {(t["startup"], t["persona"], t["territory"]) for t in tasks if t["date"] == self.day and t["bde_id"] != bde_id}
        options = planner.score_options(self.cfg, bde, self._prospects(), tasks, self.today, taken)
        return _json({"bde_id": bde_id, "linkedin_plan": bde.linkedin_plan, "daily_target": bde.daily_target, "options": options[:limit]})

    def assign_task(self, bde_id: str, startup: str, persona: str, territory: str, target: int, reason: str, coach_note: str = "") -> str:
        """Give a BDE today's task and send it to them, with yesterday's results attached automatically.

        Args:
            bde_id: e.g. BDE-01.
            startup: one of the BDE's startups.
            persona: a persona id from that startup's playbook.
            territory: a territory with weight above 0 in that playbook.
            target: number of people to find; between 5 and 120% of the BDE's daily_target.
            reason: one sentence on why this assignment, for the audit log.
            coach_note: optional short, specific, encouraging guidance for the BDE (max 400 characters),
                e.g. about yesterday's main rejection reason. Plain language; the BDE's first language may not be English.
        """
        bde = self.cfg.bdes.get(bde_id)
        if not bde:
            raise ToolRefused(f"unknown bde_id {bde_id!r}")
        if startup not in bde.startups:
            raise ToolRefused(f"{bde_id} works on {list(bde.startups)}, not {startup!r}")
        pb = self.cfg.playbooks[startup]
        if persona not in pb.personas:
            raise ToolRefused(f"{persona!r} is not a {startup} persona; choose from {sorted(pb.personas)}")
        if pb.territory_weights.get(territory, 0) <= 0:
            raise ToolRefused(f"{territory!r} is not an active territory for {startup}; choose from {sorted(k for k, v in pb.territory_weights.items() if v > 0)}")
        if not 5 <= target <= round(bde.daily_target * 1.2):
            raise ToolRefused(f"target must be between 5 and {round(bde.daily_target * 1.2)}")
        if len(coach_note) > MAX_COACH_NOTE:
            raise ToolRefused(f"coach_note is {len(coach_note)} characters; keep it under {MAX_COACH_NOTE}")
        tasks = self.store.read_tasks()
        today_tasks = [t for t in tasks if t["date"] == self.day]
        if any(t["bde_id"] == bde_id for t in today_tasks):
            raise ToolRefused(f"{bde_id} already has a task today")
        if any((t["startup"], t["persona"], t["territory"]) == (startup, persona, territory) for t in today_tasks):
            raise ToolRefused("another BDE already has this startup/persona/territory today; pick a different persona or territory")

        task = planner.make_task(bde, self.today, startup, persona, territory, target)
        self.store.append_tasks([task.as_row()])
        prev_task_ids = {t["task_id"] for t in tasks if t["bde_id"] == bde_id and t["date"] == planner.yesterday(self.today)}
        prev_rows = [r for r in self._prospects() if r["task_id"] in prev_task_ids]
        feedback = checker.summarize_by_bde(prev_rows).get(bde_id)
        body = messages.task_message(task, self.cfg, feedback, self.sheet_url, coach_note)
        result = self._deliver(bde_id, f"Today's prospecting task ({task.task_id})", body, bde.channel, bde.contact)
        self._record("assign_task", bde_id=bde_id, startup=startup, persona=persona, territory=territory, target=target, reason=reason)
        return _json({"ok": True, "task_id": task.task_id, "delivery": result})

    # ---------- tools: evening checks ----------

    def get_rows_to_check(self, limit: int = 60) -> str:
        """Rows the BDEs added that haven't been checked yet, each with the result of the automatic rules
        (required fields, profile URL, duplicates, do-not-contact, territory, company size, title keywords).
        rule_status "rejected" is final. "valid" can still be made stricter by you. "needs_review" means the
        rules couldn't tell whether the title fits the persona: that's for you to judge.

        Args:
            limit: maximum rows to return.
        """
        rows = self._prospects(refresh=True)
        updates = checker.Checker(self.cfg, use_llm=False).check(rows, self.store.read_do_not_contact(), self.day)
        self.rule_results = {n: (u["check_status"], u["check_reasons"]) for n, u in updates.items()}
        by_row = self._by_row()
        out = []
        for n, (status, reasons) in list(self.rule_results.items())[:limit]:
            item = _person(by_row[n])
            item["rule_status"], item["rule_reasons"] = status, reasons
            if status == sheet.NEEDS_REVIEW:
                p = self.cfg.playbooks[by_row[n]["startup"]].personas[by_row[n]["persona"]]
                item["persona_definition"] = {"label": p.label, "role": p.role, "example_titles": list(p.search_titles)}
            out.append(item)
        counts = Counter(s for s, _ in self.rule_results.values())
        return _json({"total_unchecked": len(self.rule_results), "by_rule_status": counts, "rows": out})

    def apply_rule_results(self, except_rows: list[int] | None = None) -> str:
        """Save the automatic rules' result for every unchecked row whose result is definite (valid or
        rejected), except rows you list. Rows whose title fit is unclear are left for record_check_decisions.

        Args:
            except_rows: rows you want to decide yourself instead (for example, a "valid" row you think is wrong).
        """
        if not self.rule_results:
            raise ToolRefused("call get_rows_to_check first")
        skip = set(except_rows or [])
        applied = Counter()
        updates = {}
        for n, (status, reasons) in self.rule_results.items():
            if n in skip or status == sheet.NEEDS_REVIEW:
                continue
            updates[n] = self._check_update(n, status, reasons)
            applied[status] += 1
        self._save_checks(updates, "rules")
        left = [n for n, (s, _) in self.rule_results.items() if n not in updates]
        return _json({"applied": applied, "rows_still_needing_your_decision": left})

    def record_check_decisions(self, decisions: list[CheckDecision]) -> str:
        """Record your decision on unchecked rows. Use needs_review when you aren't confident: a human
        will decide. You can't mark valid a row the rules rejected.

        Args:
            decisions: one per row: row number, status (valid, rejected or needs_review), and a short reason
                the BDE can learn from (required unless valid).
        """
        if not self.rule_results:
            raise ToolRefused("call get_rows_to_check first")
        updates, refused = {}, []
        for d in decisions:
            n, status, reason = d["row"], d["status"], d.get("reason", "").strip()
            if n not in self.rule_results:
                row = self._by_row().get(n)
                if row and row["check_status"]:
                    why = f"already checked as {row['check_status']} ({row['check_reasons'] or 'no reasons'}); only a human can change it, in the sheet"
                else:
                    why = "not an unchecked row; call get_rows_to_check again"
                refused.append({"row": n, "why": why})
                continue
            rule_status, rule_reasons = self.rule_results[n]
            if rule_status == sheet.REJECTED and status != sheet.REJECTED:
                refused.append({"row": n, "why": f"the rules rejected it ({rule_reasons}); that can't be overridden"})
                continue
            if status != sheet.VALID and not reason:
                refused.append({"row": n, "why": "a reason is required"})
                continue
            reasons = "; ".join(x for x in (rule_reasons, reason) if x) if status != sheet.VALID else ""
            updates[n] = self._check_update(n, status, reasons)
        self._save_checks(updates, "agent")
        return _json({"recorded": len(updates), "refused": refused})

    def _check_update(self, n, status, reasons):
        upd = {"check_status": status, "check_reasons": reasons}
        if status == sheet.VALID:
            row = self._by_row()[n]
            pb = self.cfg.playbooks[row["startup"]]
            upd.update(score=str(checker.score_row(row, pb.personas[row["persona"]], pb)), status=sheet.NEW, status_updated=self.day)
        return upd

    def _save_checks(self, updates, by):
        if not updates:
            return
        self.store.update_prospects(updates)
        for n, upd in updates.items():
            self.rule_results.pop(n, None)
            self._record("check", row=n, status=upd["check_status"], by=by)
        self._prospects(refresh=True)

    # ---------- tools: founder invites ----------

    def get_founder_candidates(self, startup: str, limit: int = 25) -> str:
        """Prospects ready for a founder's invite list, best first: valid, not yet queued, re-checked
        against the do-not-contact list. Includes how many invites the founder may still get today.

        Args:
            startup: playbook id, e.g. daxa.
            limit: maximum candidates to return.
        """
        pb = self.cfg.playbooks.get(startup)
        if not pb:
            raise ToolRefused(f"unknown startup {startup!r}")
        rows = self._prospects(refresh=True)
        cands = founder.eligible(pb, rows, self.store.read_do_not_contact())
        queued_today = sum(1 for r in rows if r["startup"] == startup and r["status"] == sheet.QUEUED and r["status_updated"] == self.day)
        return _json({
            "startup": startup, "product": pb.one_liner, "founder": pb.founder_name,
            "remaining_invites_today": max(pb.daily_invites - queued_today, 0),
            "candidates": [dict(_person(r), score=founder.row_score(r, pb)) for r in cands[:limit]],
        })

    def draft_invite_note(self, row: int) -> str:
        """Hand one prospect to the note-writer specialist, which drafts the founder's LinkedIn connection
        note from the prospect's title, company and signal notes only. Returns the note and any guardrail
        problems. You may edit the note before queueing it.

        Args:
            row: the prospect's row number.
        """
        r = self._by_row().get(row)
        if not r or r["check_status"] != sheet.VALID:
            raise ToolRefused(f"row {row} is not a valid prospect")
        pb = self.cfg.playbooks[r["startup"]]
        if llm.available():
            try:
                note, source = llm.draft_note(r, pb.personas[r["persona"]], pb), "note-writer"
            except llm.Unavailable as e:
                note, source = founder.template_note(r, pb), f"template ({e})"
        else:
            note, source = founder.template_note(r, pb), "template (Claude not configured)"
        return _json({"row": row, "note": note, "source": source, "problems": founder.note_problems(note, r), "limit": llm.NOTE_LIMIT})

    def queue_founder_invites(self, startup: str, invites: list[Invite], message_to_founder: str = "") -> str:
        """Queue today's invites for a founder and send them the list. Each row must be an eligible
        candidate and each note must pass the guardrails (max 200 characters, uses the first name, no links
        or placeholders). Call once per startup.

        Args:
            startup: playbook id.
            invites: rows with the note to send, best first.
            message_to_founder: optional one or two sentences shown at the top, e.g. why these people today.
        """
        pb = self.cfg.playbooks.get(startup)
        if not pb:
            raise ToolRefused(f"unknown startup {startup!r}")
        rows = self._prospects(refresh=True)
        allowed = {r["_row"]: r for r in founder.eligible(pb, rows, self.store.read_do_not_contact())}
        queued_today = sum(1 for r in rows if r["startup"] == startup and r["status"] == sheet.QUEUED and r["status_updated"] == self.day)
        remaining = pb.daily_invites - queued_today
        if remaining <= 0:
            raise ToolRefused(f"{startup}'s founder already has {queued_today} invites today (limit {pb.daily_invites})")
        if len(invites) > remaining:
            raise ToolRefused(f"only {remaining} more invites allowed today for {startup}; send at most {remaining}")
        problems = []
        for inv in invites:
            r = allowed.get(inv["row"])
            if not r:
                problems.append({"row": inv["row"], "why": "not an eligible candidate (not valid, already queued, excluded or on do-not-contact)"})
            else:
                for p in founder.note_problems(inv["note"].strip(), r):
                    problems.append({"row": inv["row"], "why": f"note {p}"})
        if problems:
            raise ToolRefused("nothing queued; fix these and call again: " + _json(problems))
        updates = {inv["row"]: {"founder_note": inv["note"].strip(), "status": sheet.QUEUED, "status_updated": self.day} for inv in invites}
        self.store.update_prospects(updates)
        self._prospects(refresh=True)
        body = messages.founder_message(pb, [(allowed[i["row"]], i["note"].strip()) for i in invites], self.day)
        if message_to_founder:
            body = message_to_founder.strip() + "\n\n" + body
        result = self._deliver(f"founder-{startup}", f"{pb.name}: today's LinkedIn invites", body, pb.founder_channel, pb.founder_contact)
        self._record("queue_founder_invites", startup=startup, rows=[i["row"] for i in invites])
        return _json({"ok": True, "queued": len(invites), "delivery": result})

    # ---------- tools: handoff to the owner, report, memory ----------

    def escalate_to_human(self, question: str, rows: list[int] | None = None, urgency: Literal["low", "normal", "high"] = "normal") -> str:
        """Hand a decision to the owner when you're not confident or it's outside your authority: an
        unclear prospect, a BDE problem, a playbook that seems wrong, a founder not acting on invites.
        Unchecked rows you list are marked needs_review. Delivered at the end of this run.

        Args:
            question: what you need decided, with the evidence, in two or three sentences.
            rows: related row numbers, if any.
            urgency: high only if something is going wrong today.
        """
        rows = rows or []
        pending = {n: self._check_update(n, sheet.NEEDS_REVIEW, "sent to owner: " + question[:150]) for n in rows if n in self.rule_results}
        self._save_checks(pending, "agent")
        self.escalations.append({"question": question, "rows": rows, "urgency": urgency})
        self._record("escalate", rows=rows, urgency=urgency)
        return _json({"ok": True, "will_be_sent_to": self.cfg.owner.name})

    def send_weekly_report(self, analysis: str, proposed_changes: list[str]) -> str:
        """Send the owner the weekly report: standard tables plus your analysis and proposed changes.
        You can't change playbooks or assignments rules yourself; propose them here for the owner to approve.

        Args:
            analysis: your markdown analysis: what's working, what isn't, and why, with numbers.
            proposed_changes: concrete changes, each one line, e.g. "daxa: lower data_governance priority to 1 (2/25 accepted)".
        """
        end = self.today - timedelta(days=1)
        start = end - timedelta(days=6)
        tables = messages.weekly_report(self.cfg, self._prospects(), start.isoformat(), end.isoformat())
        changes = "\n".join(f"- [ ] {c}" for c in proposed_changes) or "- None this week."
        body = f"## Agent's analysis\n\n{analysis.strip()}\n\n## Proposed changes (for you to approve)\n\n{changes}\n\n{tables}"
        result = self._deliver("weekly-report", "Weekly BDE prospecting report", body, self.cfg.owner.channel, self.cfg.owner.contact)
        self._record("weekly_report", proposed_changes=len(proposed_changes))
        return _json({"ok": True, "delivery": result})

    def write_journal(self, note: str) -> str:
        """Leave a note for your next run: what you decided and why, what to watch, open questions.
        Your next run sees the last five notes in get_situation.

        Args:
            note: under 1500 characters.
        """
        if len(note) > MAX_JOURNAL_NOTE:
            raise ToolRefused(f"note is {len(note)} characters; keep it under {MAX_JOURNAL_NOTE}")
        self.store.append_agent_log({"date": self.day, "mode": self.mode, "note": note.strip()})
        self._record("journal")
        return _json({"ok": True})

    # ---------- per-mode access and completion checks ----------

    READ_TOOLS = ["get_situation", "get_bde_history", "get_performance"]
    MODE_TOOLS = {
        "morning": READ_TOOLS + ["get_assignment_options", "assign_task", "escalate_to_human", "write_journal"],
        "evening": READ_TOOLS + ["get_rows_to_check", "apply_rule_results", "record_check_decisions",
                                 "get_founder_candidates", "draft_invite_note", "queue_founder_invites",
                                 "escalate_to_human", "write_journal"],
        "weekly": READ_TOOLS + ["send_weekly_report", "escalate_to_human", "write_journal"],
        "ask": READ_TOOLS + ["get_assignment_options", "get_founder_candidates"],
    }

    def tools_for(self, mode):
        """Least privilege: each mode only gets the tools it needs."""
        return [getattr(self, name) for name in self.MODE_TOOLS[mode]]

    def open_items(self):
        """What the run was supposed to finish but hasn't. Used to nudge the agent once before it stops."""
        items = []
        if self.mode == "morning":
            tasks_today = {t["bde_id"] for t in self.store.read_tasks() if t["date"] == self.day}
            missing = sorted(set(self.cfg.bdes) - tasks_today)
            if missing:
                items.append(f"BDEs without a task today: {', '.join(missing)}")
        if self.mode == "evening":
            unchecked = [r["_row"] for r in self._prospects(refresh=True) if r["check_status"] == sheet.PENDING]
            if unchecked:
                items.append(f"rows still unchecked: {unchecked[:20]}")
            rows = self._prospects()
            for pb in self.cfg.playbooks.values():
                queued = any(r["startup"] == pb.id and r["status"] == sheet.QUEUED and r["status_updated"] == self.day for r in rows)
                if not queued and founder.eligible(pb, rows, self.store.read_do_not_contact()):
                    items.append(f"{pb.id}: eligible prospects but no invites queued today")
        if self.mode == "weekly" and not any(a["action"] == "weekly_report" for a in self.actions):
            items.append("weekly report not sent")
        if self.mode != "ask" and not any(a["action"] == "journal" for a in self.actions):
            items.append("no journal note written for your next run")
        return items

    def deliver_escalations(self):
        """Send everything escalated this run, plus rows the rules sent to review, to the owner in one message."""
        review_rows = [r for r in self._prospects(refresh=True) if r["check_status"] == sheet.NEEDS_REVIEW]
        if not self.escalations and not review_rows:
            return None
        lines = []
        for e in sorted(self.escalations, key=lambda e: {"high": 0, "normal": 1, "low": 2}[e["urgency"]]):
            rows = f" (rows {', '.join(map(str, e['rows']))})" if e["rows"] else ""
            lines.append(f"- **[{e['urgency']}]** {e['question']}{rows}")
        if review_rows:
            lines += ["", "Rows waiting for your decision (set `check_status` to `valid` or `rejected`):"]
            lines += [f"- Row {r['_row']} ({r['bde_id']}): {r['first_name']} {r['last_name']}, {r['title']} at {r['company']}: {r['check_reasons']}" for r in review_rows]
        return notify.deliver(self.outbox, self.day, "owner-review", "Decisions needed from you", "\n".join(lines),
                              self.cfg.owner.channel, self.cfg.owner.contact, self.send)
