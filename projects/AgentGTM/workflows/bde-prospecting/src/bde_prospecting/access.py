"""Who can sign in to the web app, what they see, and what they can change.

Every check happens on the server. The page only shows buttons a person may use, but each
action is re-checked here against the signed-in email.

- Owner (emails in config/bdes.toml [owner]): all startups, review queue, agent activity.
- Founder (emails in playbooks/<startup>.toml founder_emails): only their startup's prospects,
  and only status changes along the pipeline.
- Anyone else: no access.
"""

from dataclasses import dataclass

from . import checker, sheet

# Founder status changes allowed from each stage. "do_not_contact" is always allowed.
TRANSITIONS = {
    sheet.QUEUED: [sheet.INVITED, sheet.NOT_A_FIT],
    sheet.INVITED: [sheet.ACCEPTED, sheet.NOT_A_FIT],
    sheet.ACCEPTED: [sheet.REPLIED, sheet.NOT_A_FIT],
    sheet.REPLIED: [sheet.MEETING, sheet.NOT_A_FIT],
    sheet.MEETING: [],
}
LABELS = {
    sheet.INVITED: "Sent invite", sheet.ACCEPTED: "Accepted", sheet.REPLIED: "Replied",
    sheet.MEETING: "Meeting booked", sheet.NOT_A_FIT: "Not a fit", sheet.DNC: "Don't contact",
}


class AccessDenied(Exception):
    pass


@dataclass(frozen=True)
class Viewer:
    email: str
    is_owner: bool
    startups: tuple[str, ...]  # startups this person may see

    def can_see(self, startup):
        return self.is_owner or startup in self.startups


def resolve_viewer(cfg, email, email_verified=True):
    """Return the Viewer for a signed-in email, or None if they have no access."""
    if not email or not email_verified:
        return None
    email = email.strip().lower()
    is_owner = email in cfg.owner.emails
    startups = tuple(sorted(pb.id for pb in cfg.playbooks.values() if email in pb.founder_emails))
    if not is_owner and not startups:
        return None
    return Viewer(email, is_owner, tuple(sorted(cfg.playbooks)) if is_owner else startups)


def allowed_next(status):
    return TRANSITIONS.get(status, []) + ([sheet.DNC] if status in TRANSITIONS else [])


def update_status(viewer, cfg, store, row_number, new_status, today):
    """A founder (or the owner) records what happened with an invite."""
    row = {r["_row"]: r for r in store.read_prospects()}.get(row_number)
    if row is None:
        raise AccessDenied("row not found")
    if not viewer.can_see(row["startup"]):
        raise AccessDenied("this prospect belongs to another startup")
    if new_status not in allowed_next(row["status"]):
        raise AccessDenied(f"can't move from {row['status'] or 'new'} to {new_status}")
    store.update_prospects({row_number: {"status": new_status, "status_updated": today}})
    if new_status == sheet.DNC:
        store.append_do_not_contact({
            "linkedin_url": row["linkedin_url"], "company_domain": "", "company": "",
            "reason": f"marked by {viewer.email}", "added_by": viewer.email, "date": today,
        })
    return row


def decide_review(viewer, cfg, store, row_number, decision, reason, today):
    """The owner resolves a row the agent or the rules sent for review."""
    if not viewer.is_owner:
        raise AccessDenied("only the owner can decide review rows")
    row = {r["_row"]: r for r in store.read_prospects()}.get(row_number)
    if row is None or row["check_status"] != sheet.NEEDS_REVIEW:
        raise AccessDenied("row is not waiting for review")
    if decision == sheet.VALID:
        pb = cfg.playbooks[row["startup"]]
        score = checker.score_row(row, pb.personas[row["persona"]], pb)
        update = {"check_status": sheet.VALID, "check_reasons": "", "score": str(score), "status": sheet.NEW, "status_updated": today}
    elif decision == sheet.REJECTED:
        if not reason.strip():
            raise AccessDenied("give the BDE a reason")
        update = {"check_status": sheet.REJECTED, "check_reasons": f"owner: {reason.strip()}", "status_updated": today}
    else:
        raise AccessDenied(f"unknown decision {decision!r}")
    store.update_prospects({row_number: update})
    return row
