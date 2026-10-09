"""Nightly check of new BDE rows: validate, dedupe, match persona and territory, score.

Only rows with an empty check_status are checked. A BDE resubmits a fixed row by
clearing its check_status.
"""

import re
from collections import Counter, defaultdict
from datetime import date

from . import llm, sheet

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "district of columbia": "DC", "washington dc": "DC", "washington d.c.": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA",
    "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN",
    "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}
STATE_CODES = set(US_STATES.values())

PROFILE_RE = re.compile(r"^(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/([^/?#\s]+)/?(?:[?#].*)?$", re.I)


def normalize_linkedin(url):
    """Return the canonical public profile URL, or None if it isn't one."""
    m = PROFILE_RE.match(url.strip())
    if not m:
        return None
    return f"https://www.linkedin.com/in/{m.group(1).lower()}"


def normalize_state(value):
    v = value.strip()
    if v.upper() in STATE_CODES:
        return v.upper()
    return US_STATES.get(v.lower())


def normalize_domain(value):
    v = value.strip().lower()
    v = re.sub(r"^https?://", "", v)
    v = v.removeprefix("www.")
    return v.split("/")[0]


def _contains_any(text, keywords):
    """Keyword match on word boundaries, so "cto" doesn't match "director".

    A keyword ending in "*" matches the start of a word: "recruit*" matches "recruiter".
    """
    for k in keywords:
        stem = k.endswith("*")
        end = "" if stem else r"(?![a-z0-9])"
        if re.search(rf"(?<![a-z0-9]){re.escape(k.rstrip('*'))}{end}", text):
            return True
    return False


def match_title(title, persona):
    """Rule-based persona match: "match", "no_match" or "unclear"."""
    t = " ".join(title.lower().replace(",", " ").split())
    keywords = [" ".join(k.replace(",", " ").split()) for k in persona.title_keywords]
    if _contains_any(t, persona.exclude_title_keywords):
        return "no_match"
    if _contains_any(t, keywords):
        if persona.require_title_keywords and not _contains_any(t, persona.require_title_keywords):
            return "unclear"
        return "match"
    return "unclear"


def score_row(row, persona, playbook):
    """0-100 priority for the founder's invite queue."""
    score = 20 * persona.priority  # up to 60
    score += 5 * min(playbook.territory_weights.get(row["territory"], 0), 3)  # up to 15
    if row["industry"] and row["industry"] in playbook.preferred_industries:
        score += 10
    if len(row.get("signal_notes", "").strip()) >= 15:
        score += 15
    return int(min(score, 100))


def do_not_contact_matcher(dnc_rows):
    """Return a function telling whether a row matches the do-not-contact list."""
    urls = {normalize_linkedin(r["linkedin_url"]) for r in dnc_rows if r["linkedin_url"]} - {None}
    domains = {normalize_domain(r["company_domain"]) for r in dnc_rows if r["company_domain"]}
    companies = {r["company"].strip().lower() for r in dnc_rows if r["company"]}

    def blocked(row):
        url = normalize_linkedin(row["linkedin_url"]) if row["linkedin_url"].strip() else None
        domain = normalize_domain(row["company_domain"]) if row["company_domain"] else ""
        company = row["company"].strip().lower()
        return bool((url and url in urls) or (domain and domain in domains) or (company and company in companies))

    return blocked


class Checker:
    def __init__(self, cfg, use_llm=None):
        self.cfg = cfg
        self.use_llm = llm.available() if use_llm is None else use_llm
        self.llm_calls = 0

    def check(self, rows, dnc_rows, today=None):
        """Return {row number: agent column updates} for unchecked rows."""
        today = today or date.today().isoformat()
        blocked = do_not_contact_matcher(dnc_rows)

        # Earlier rows that weren't rejected claim their URL and name+company first.
        seen_urls, seen_people = {}, {}
        updates = {}
        for row in rows:
            fresh = row["check_status"] == sheet.PENDING
            if fresh:
                status, reasons, extra = self._check_row(row, seen_urls, seen_people, blocked)
                updates[row["_row"]] = {"check_status": status, "check_reasons": "; ".join(reasons), **extra}
                if status == sheet.VALID:
                    updates[row["_row"]].update(status=sheet.NEW, status_updated=today)
            else:
                status = row["check_status"]
            if status != sheet.REJECTED:
                url = normalize_linkedin(row["linkedin_url"])
                if url:
                    seen_urls.setdefault(url, row["_row"])
                seen_people.setdefault(self._person_key(row), row["_row"])
        return updates

    @staticmethod
    def _person_key(row):
        name = f"{row['first_name']} {row['last_name']}".strip().lower()
        return name, row["company"].strip().lower()

    def _check_row(self, row, seen_urls, seen_people, blocked):
        errors, review = [], []
        missing = [c for c in sheet.REQUIRED if not row[c].strip()]
        if missing:
            errors.append("missing " + ", ".join(missing))

        url = normalize_linkedin(row["linkedin_url"]) if row["linkedin_url"].strip() else None
        if row["linkedin_url"].strip() and not url:
            if "/sales/" in row["linkedin_url"]:
                errors.append("Sales Navigator link: paste the public profile URL (linkedin.com/in/...)")
            else:
                errors.append("linkedin_url is not a profile URL (linkedin.com/in/...)")
        if url and url in seen_urls:
            errors.append(f"duplicate of row {seen_urls[url]}")
        elif all(row[c].strip() for c in ("first_name", "last_name", "company")) and self._person_key(row) in seen_people:
            errors.append(f"same person and company as row {seen_people[self._person_key(row)]}")

        domain = normalize_domain(row["company_domain"]) if row["company_domain"] else ""
        company = row["company"].strip().lower()
        if blocked(row):
            errors.append("on the do-not-contact list")

        if row["bde_id"] and row["bde_id"] not in self.cfg.bdes:
            errors.append(f"unknown bde_id {row['bde_id']!r}")
        playbook = self.cfg.playbooks.get(row["startup"])
        if row["startup"] and not playbook:
            errors.append(f"unknown startup {row['startup']!r}")
        persona = playbook.personas.get(row["persona"]) if playbook else None
        if playbook and row["persona"] and not persona:
            errors.append(f"persona {row['persona']!r} is not one of {row['startup']}'s personas")
        territory = self.cfg.territories.get(row["territory"])
        if row["territory"] and not territory:
            errors.append(f"unknown territory {row['territory']!r}")

        if playbook and (company in playbook.exclude_companies or (domain and domain in playbook.exclude_companies)):
            errors.append(f"{row['company']} is excluded for {playbook.name} (customer, competitor or partner)")

        if territory and row["state"].strip():
            state = normalize_state(row["state"])
            if not state:
                errors.append(f"state {row['state']!r} is not a US state")
            elif state not in territory.states:
                errors.append(f"{state} is outside territory {territory.id}")

        if persona and row["company_size"] and persona.company_sizes and row["company_size"] not in persona.company_sizes:
            errors.append(f"company size {row['company_size']} is outside {persona.id}'s target ({', '.join(persona.company_sizes)})")

        if persona and row["title"].strip() and not errors:
            verdict = match_title(row["title"], persona)
            if verdict == "no_match":
                errors.append(f"title {row['title']!r} doesn't fit persona {persona.id}")
            elif verdict == "unclear":
                outcome = self._ask_llm(row, persona, playbook)
                if outcome is None:
                    review.append(f"title {row['title']!r} may not fit persona {persona.id}; please confirm")
                elif not outcome["fits"]:
                    errors.append(f"title {row['title']!r} doesn't fit persona {persona.id} ({outcome['reason']})")
                elif outcome["confidence"] == "low":
                    review.append(f"title fit is uncertain: {outcome['reason']}")

        if errors:
            return sheet.REJECTED, errors, {}
        if review:
            return sheet.NEEDS_REVIEW, review, {}
        return sheet.VALID, [], {"score": str(score_row(row, persona, playbook))}

    def _ask_llm(self, row, persona, playbook):
        if not self.use_llm:
            return None
        try:
            self.llm_calls += 1
            return llm.classify_title(row["title"], persona, playbook)
        except llm.Unavailable:
            return None


def summarize_by_bde(rows):
    """Per-BDE counts and most common rejection reasons for rows that have been checked."""
    stats = defaultdict(lambda: {"checked": 0, sheet.VALID: 0, sheet.REJECTED: 0, sheet.NEEDS_REVIEW: 0, "reasons": Counter()})
    for row in rows:
        if row["check_status"] not in sheet.CHECK_STATUSES:
            continue
        s = stats[row["bde_id"] or "unknown"]
        s["checked"] += 1
        s[row["check_status"]] += 1
        if row["check_status"] == sheet.REJECTED:
            for reason in row["check_reasons"].split("; "):
                s["reasons"][reason_kind(reason)] += 1
    return dict(stats)


def reason_kind(reason):
    """Group reasons so feedback reads "duplicate (4)", not four separate row numbers."""
    for prefix in ("duplicate", "same person", "title", "company size", "missing", "Sales Navigator link", "on the do-not-contact"):
        if reason.startswith(prefix):
            return {"same person": "duplicate", "on the do-not-contact": "do-not-contact"}.get(prefix, prefix)
    if "outside territory" in reason:
        return "outside territory"
    return reason
