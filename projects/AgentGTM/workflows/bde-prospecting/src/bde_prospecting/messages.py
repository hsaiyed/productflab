"""Text of the messages the workflow sends: BDE tasks, founder invite batches, weekly report."""

from collections import Counter, defaultdict

from . import sheet
from .checker import normalize_linkedin, reason_kind


def _or_query(terms):
    return " OR ".join(f'"{t}"' for t in terms)


def task_message(task, cfg, feedback=None, sheet_url="", coach_note=""):
    bde = cfg.bdes[task.bde_id]
    pb = cfg.playbooks[task.startup]
    persona = pb.personas[task.persona]
    territory = cfg.territories[task.territory]
    sizes = ", ".join(persona.company_sizes) or "any"
    lines = [
        f"**{task.date} task for {bde.id}{' (' + bde.name + ')' if bde.name and bde.name != 'TBD' else ''}** · `{task.task_id}`",
        "",
        f"- **Startup:** {pb.name}: {pb.one_liner}",
        f"- **Persona:** {persona.label}",
        f"- **Territory:** {territory.label} ({', '.join(territory.metros)})",
        f"- **Company size:** {sizes}",
        f"- **Target:** {task.target} people",
        "",
    ]
    if task.mode == "sales_navigator":
        lines += [
            "**Sales Navigator lead filters**",
            f"- Current job title: {_or_query(persona.search_titles)}",
            f"- Geography: {', '.join(territory.metros)}",
            f"- Company headcount: {sizes}",
        ]
        if pb.preferred_industries:
            lines.append(f"- Industry (preferred): {', '.join(pb.preferred_industries)}")
        lines += ["- Copy the person's **public** profile URL (linkedin.com/in/...), not the Sales Navigator link.", ""]
    else:
        metros = _or_query(territory.metros)
        lines += [
            "**Google search** (saves your LinkedIn free search limit; paste into google.com):",
            f"```\nsite:linkedin.com/in ({_or_query(persona.search_titles)}) ({metros})\n```",
            "Open each result, confirm the current title, company and location on LinkedIn, then add the row.",
            "",
        ]
    lines += [
        "**For every row:** fill all columns, use the dropdowns, put this task id in `task_id`.",
        "**Bonus:** note anything recent and relevant in `signal_notes` (a post, a new role, hiring, a launch).",
        "**Skip:** anyone in the DoNotContact tab and any company you're unsure about.",
    ]
    if pb.exclude_companies:
        lines.append(f"**Never add people from:** {', '.join(pb.exclude_companies)} (customers, competitors or partners).")
    if coach_note:
        lines += ["", f"**Note for you today:** {coach_note}"]
    if feedback:
        lines += ["", "**Yesterday's results:** " + _feedback_line(feedback)]
    if sheet_url:
        lines += ["", f"Sheet: {sheet_url}"]
    return "\n".join(lines)


def _feedback_line(stats):
    line = f"{stats['checked']} checked: {stats[sheet.VALID]} valid ✅, {stats[sheet.REJECTED]} rejected"
    if stats[sheet.NEEDS_REVIEW]:
        line += f", {stats[sheet.NEEDS_REVIEW]} sent for review"
    if stats["reasons"]:
        top = ", ".join(f"{reason} ({n})" for reason, n in stats["reasons"].most_common(3))
        line += f". Main rejection reasons: {top}"
    return line + "."


def founder_message(playbook, picks, day):
    lines = [
        f"**{playbook.name}: {len(picks)} LinkedIn invites for {day}**",
        "",
        "Send each from your own LinkedIn (about 10 minutes). Edit the note if anything is off.",
        "Then set `status` in the sheet to `invited` (or `not_a_fit` if you skip someone).",
        "",
    ]
    for i, (row, note) in enumerate(picks, 1):
        lines += [
            f"{i}. **{row['first_name']} {row['last_name']}**, {row['title']} at {row['company']} ({row['city']}, {row['state']})",
            f"   {normalize_linkedin(row['linkedin_url']) or row['linkedin_url']}",
            f"   Note: {note}",
        ]
    return "\n".join(lines)


def weekly_report(cfg, rows, start, end):
    """Markdown report for [start, end] (ISO dates, inclusive)."""
    in_week = [r for r in rows if start <= r["date_added"] <= end]
    lines = [f"Period: {start} to {end}", "", "## BDE quality", "",
             "| BDE | Rows added | Valid | Rejected | Needs review | Valid rate | Top rejection reason |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    by_bde = defaultdict(list)
    for r in in_week:
        by_bde[r["bde_id"]].append(r)
    for bde_id in sorted(set(cfg.bdes) | set(by_bde)):
        rs = by_bde.get(bde_id, [])
        counts = Counter(r["check_status"] for r in rs)
        checked = counts[sheet.VALID] + counts[sheet.REJECTED]
        rate = f"{counts[sheet.VALID] / checked:.0%}" if checked else "—"
        reasons = Counter(reason_kind(reason) for r in rs if r["check_status"] == sheet.REJECTED for reason in r["check_reasons"].split("; "))
        top = reasons.most_common(1)[0][0] if reasons else "—"
        lines.append(f"| {bde_id} | {len(rs)} | {counts[sheet.VALID]} | {counts[sheet.REJECTED]} | {counts[sheet.NEEDS_REVIEW]} | {rate} | {top} |")

    lines += ["", "## Funnel by startup and persona (all time)", "",
              "| Startup | Persona | Valid | Invited | Accepted | Replied | Meetings | Accept rate |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    funnel = defaultdict(Counter)
    for r in rows:
        if r["check_status"] != sheet.VALID:
            continue
        f = funnel[(r["startup"], r["persona"])]
        f["valid"] += 1
        f["invited"] += r["status"] in sheet.SENT_STAGES
        f["accepted"] += r["status"] in sheet.ACCEPTED_STAGES
        f["replied"] += r["status"] in {sheet.REPLIED, sheet.MEETING}
        f["meeting"] += r["status"] == sheet.MEETING
    for (sid, pid), f in sorted(funnel.items()):
        rate = f"{f['accepted'] / f['invited']:.0%}" if f["invited"] else "—"
        lines.append(f"| {sid} | {pid} | {f['valid']} | {f['invited']} | {f['accepted']} | {f['replied']} | {f['meeting']} | {rate} |")

    suggestions = []
    for (sid, pid), f in sorted(funnel.items()):
        if f["invited"] >= 20 and f["accepted"] / f["invited"] < 0.15:
            suggestions.append(f"- **{sid} / {pid}:** only {f['accepted']}/{f['invited']} invites accepted. Consider lowering its priority or revising the note.")
        backlog = f["valid"] - f["invited"]
        if sid in cfg.playbooks and backlog > 3 * cfg.playbooks[sid].daily_invites:
            suggestions.append(f"- **{sid} / {pid}:** {backlog} valid prospects not yet invited. The founder is the bottleneck; consider fewer BDE hours on it.")
    unconfirmed = [pb.name for pb in cfg.playbooks.values() if not pb.confirmed]
    if unconfirmed:
        suggestions.append(f"- Playbooks still unconfirmed with founders: {', '.join(unconfirmed)}.")
    lines += ["", "## Suggestions for you to decide", ""] + (suggestions or ["- Nothing stands out this week."])
    lines += ["", "_The agent doesn't change playbooks or assignments itself. Edit the playbook files to act on a suggestion._"]
    return "\n".join(lines)
