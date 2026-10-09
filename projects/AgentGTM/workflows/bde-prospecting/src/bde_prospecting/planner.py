"""Daily task planner: picks a (startup, persona, territory) focus for each BDE.

The weight of each option is

    persona priority × territory weight × coverage × performance × freshness

- coverage: options with fewer valid rows in the last 14 days get more weight
- performance: once a persona has 10+ sent invites, its acceptance rate scales the
  weight up or down (between 0.5x and 2x)
- freshness: options assigned in the last 3 days get less weight, so work rotates

No two BDEs get the same option on the same day. The choice is deterministic for a
given sheet and date, so a re-run produces the same plan.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from . import sheet

BASELINE_ACCEPT_RATE = 0.3
MIN_INVITES_FOR_PERFORMANCE = 10


@dataclass(frozen=True)
class Task:
    date: str
    task_id: str
    bde_id: str
    startup: str
    persona: str
    territory: str
    target: int
    mode: str  # "sales_navigator" or "google_xray"
    weight: float

    def as_row(self):
        return {c: getattr(self, c) for c in sheet.TASK_COLUMNS}


def _days_ago(day_str, today):
    try:
        return (today - date.fromisoformat(day_str)).days
    except ValueError:
        return None


def _stats(rows, tasks, today):
    recent_valid = Counter()
    sent, accepted = Counter(), Counter()
    for r in rows:
        key = (r["startup"], r["persona"], r["territory"])
        days = _days_ago(r["date_added"], today)
        if r["check_status"] == sheet.VALID and days is not None and 0 <= days <= 14:
            recent_valid[key] += 1
        if r["status"] in sheet.SENT_STAGES:
            sent[(r["startup"], r["persona"])] += 1
        if r["status"] in sheet.ACCEPTED_STAGES:
            accepted[(r["startup"], r["persona"])] += 1
    recent_tasks = Counter()
    for t in tasks:
        days = _days_ago(t["date"], today)
        if days is not None and 1 <= days <= 3:
            recent_tasks[(t["startup"], t["persona"], t["territory"])] += 1
    return recent_valid, sent, accepted, recent_tasks


def plan_day(cfg, rows, tasks, today=None):
    today = today or date.today()
    if any(t["date"] == today.isoformat() for t in tasks):
        return []  # already planned today
    recent_valid, sent, accepted, recent_tasks = _stats(rows, tasks, today)
    taken = set()
    plan = []
    for bde in sorted(cfg.bdes.values(), key=lambda b: b.id):
        options = []
        for sid in bde.startups:
            pb = cfg.playbooks[sid]
            for persona in pb.personas.values():
                n_sent = sent[(sid, persona.id)]
                if n_sent >= MIN_INVITES_FOR_PERFORMANCE:
                    rate = (accepted[(sid, persona.id)] + 1) / (n_sent + 2)
                    performance = min(max(rate / BASELINE_ACCEPT_RATE, 0.5), 2.0)
                else:
                    performance = 1.0
                for tid, tweight in pb.territory_weights.items():
                    key = (sid, persona.id, tid)
                    if tweight <= 0 or key in taken:
                        continue
                    coverage = 1 / (1 + recent_valid[key] / 50)
                    freshness = 0.5 ** recent_tasks[key]
                    weight = persona.priority * tweight * coverage * performance * freshness
                    options.append((round(weight, 6), persona.priority, sid, persona.id, tid))
        if not options:
            continue
        # Highest weight wins; ties go to the higher-priority persona, then alphabetical order.
        weight, _, sid, pid, tid = min(options, key=lambda o: (-o[0], -o[1], o[2], o[3], o[4]))
        taken.add((sid, pid, tid))
        plan.append(Task(
            date=today.isoformat(),
            task_id=f"T-{today.isoformat()}-{bde.id}",
            bde_id=bde.id,
            startup=sid,
            persona=pid,
            territory=tid,
            target=bde.daily_target,
            mode="sales_navigator" if bde.linkedin_plan == "sales_navigator" else "google_xray",
            weight=weight,
        ))
    return plan


def yesterday(today):
    return (today - timedelta(days=1)).isoformat()
