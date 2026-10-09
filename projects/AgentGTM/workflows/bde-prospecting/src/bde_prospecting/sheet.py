"""Shared sheet layout: tab names, columns and allowed values.

BDEs fill the BDE columns. The agent owns the AGENT columns, except `status`,
which founders update after acting on an invite.
"""

PROSPECTS = "Prospects"
TASKS = "Tasks"
DO_NOT_CONTACT = "DoNotContact"

BDE_COLUMNS = [
    "date_added", "bde_id", "task_id", "startup", "territory", "persona",
    "first_name", "last_name", "title", "company", "company_domain",
    "company_size", "industry", "city", "state", "linkedin_url", "signal_notes",
]
AGENT_COLUMNS = ["check_status", "check_reasons", "score", "founder_note", "status", "status_updated"]
PROSPECT_COLUMNS = BDE_COLUMNS + AGENT_COLUMNS

REQUIRED = [
    "bde_id", "startup", "territory", "persona", "first_name", "last_name", "title",
    "company", "company_size", "state", "linkedin_url",
]

TASK_COLUMNS = ["date", "task_id", "bde_id", "startup", "persona", "territory", "target", "mode"]
DNC_COLUMNS = ["linkedin_url", "company_domain", "company", "reason", "added_by", "date"]

# check_status values
PENDING, VALID, REJECTED, NEEDS_REVIEW = "", "valid", "rejected", "needs_review"
CHECK_STATUSES = ["valid", "rejected", "needs_review"]

# status values (pipeline stage). Founders move rows from "queued" onwards.
NEW, QUEUED, INVITED, ACCEPTED, REPLIED, MEETING, NOT_A_FIT, DNC = (
    "new", "queued", "invited", "accepted", "replied", "meeting", "not_a_fit", "do_not_contact",
)
STATUSES = [NEW, QUEUED, INVITED, ACCEPTED, REPLIED, MEETING, NOT_A_FIT, DNC]
# Stages that mean the invite went out, and the later ones that mean it was accepted.
SENT_STAGES = {INVITED, ACCEPTED, REPLIED, MEETING, NOT_A_FIT}
ACCEPTED_STAGES = {ACCEPTED, REPLIED, MEETING}
