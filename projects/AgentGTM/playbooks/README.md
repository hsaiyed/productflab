# Playbooks

One file per startup. Every AgentGTM workflow reads these, so keep them current.

A playbook says what the startup sells, who buys it (personas), where to look (territory weights), and who never to contact.
Fields marked `confirmed = false` are first drafts: review them with the founder, then set `confirmed = true`.

| Field | Meaning |
| --- | --- |
| `personas[].priority` | 3 = primary buyer, 2 = strong champion, 1 = nice to have. Drives how often the planner assigns it. |
| `personas[].title_keywords` | A title matching any of these (case-insensitive) fits the persona. |
| `personas[].require_title_keywords` | If set, the title must also contain one of these (e.g. seniority words). |
| `personas[].exclude_title_keywords` | A title containing any of these never fits. End a keyword with `*` to match word starts (`recruit*` matches "Recruiter"). |
| `personas[].company_sizes` | Allowed LinkedIn company-size bands. Empty = any. |
| `personas[].search_titles` | Titles BDEs paste into LinkedIn / Google searches. |
| `territory_weights` | How much to search each territory (0 = never). Territory ids are in `workflows/bde-prospecting/config/territories.toml`. |
| `founder_emails` | Google accounts allowed to sign in to this startup's founder page. |
| `exclude_companies` | Current customers, competitors, partners. Domains or names. |
