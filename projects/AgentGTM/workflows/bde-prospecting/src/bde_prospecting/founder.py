"""Pick each founder's daily invites and draft a connection note for each."""

import re

from . import llm, sheet
from .checker import do_not_contact_matcher, normalize_domain, score_row

URL_RE = re.compile(r"https?://|www\.", re.I)


def template_note(row, playbook):
    note = f"Hi {row['first_name']}, I'm building {playbook.name} and talk with a lot of {_role_word(row['title'])} leaders. Would be glad to connect."
    return note[: llm.NOTE_LIMIT]


def _role_word(title):
    t = title.lower()
    for word, label in (("security", "security"), ("ciso", "security"), ("cso", "security"), ("sre", "SRE"), ("reliability", "SRE"), ("infrastructure", "infrastructure"),
                        ("platform", "platform"), ("architect", "architecture"), ("data", "data"), ("product", "product"), ("ai", "AI")):
        if re.search(rf"(?<![a-z]){word}(?![a-z])", t):
            return label
    return "engineering"


def note_problems(note, row):
    """Guardrails every note must pass before a founder sees it."""
    problems = []
    if not note:
        problems.append("empty")
    if len(note) > llm.NOTE_LIMIT:
        problems.append(f"{len(note)} characters (limit {llm.NOTE_LIMIT})")
    if URL_RE.search(note):
        problems.append("contains a link")
    if "{" in note or "[" in note:
        problems.append("contains a placeholder")
    if row["first_name"] and row["first_name"].lower() not in note.lower():
        problems.append("doesn't use the person's first name")
    return problems


def row_score(row, playbook):
    return int(row["score"]) if row["score"].isdigit() else score_row(row, playbook.personas[row["persona"]], playbook)


def eligible(playbook, rows, dnc_rows):
    """Valid, not yet queued, and not on the do-not-contact list now (it may have changed since the check)."""
    blocked = do_not_contact_matcher(dnc_rows)
    out = [
        r for r in rows
        if r["startup"] == playbook.id and r["check_status"] == sheet.VALID and r["status"] in ("", sheet.NEW)
        and r["persona"] in playbook.personas and not blocked(r)
        and r["company"].strip().lower() not in playbook.exclude_companies
        and normalize_domain(r["company_domain"]) not in playbook.exclude_companies
    ]
    out.sort(key=lambda r: (-row_score(r, playbook), r["date_added"], r["_row"]))
    return out


def pick_and_draft(cfg, playbook, rows, use_llm=None, dnc_rows=()):
    """Return [(row, note, source)] for today's invites; source is "claude" or "template"."""
    use_llm = llm.available() if use_llm is None else use_llm
    picks = []
    for row in eligible(playbook, rows, dnc_rows)[: playbook.daily_invites]:
        note, source = None, "template"
        if use_llm:
            try:
                drafted = llm.draft_note(row, playbook.personas[row["persona"]], playbook)
                if not note_problems(drafted, row):
                    note, source = drafted, "claude"
            except llm.Unavailable:
                pass
        if note is None:
            note = template_note(row, playbook)
        picks.append((row, note, source))
    return picks
