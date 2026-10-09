# BDE guide

You research US decision-makers on LinkedIn for our startups. The founders reach out to them personally, so **accuracy matters more than volume**.

## Your day

1. **Morning (~09:30 IST):** you get today's task: which startup, which kind of person (persona), which US region, a ready-made search, and a target number. It also shows how yesterday's rows did.
2. **During the day:** search, open each profile, check it, and add one row per person to the `Prospects` tab.
3. **Evening (~20:00 IST):** the agent checks your rows. Results arrive with tomorrow's task.

## Searching

- **Sales Navigator (BDE-01):** use the lead filters in your task. Always copy the person's **public** profile URL (`linkedin.com/in/...`). Sales Navigator links (`linkedin.com/sales/...`) are rejected.
- **Free LinkedIn (BDE-02 to 04):** paste the Google search from your task into google.com. This doesn't use up your LinkedIn search limit. Open each result on LinkedIn to confirm the person still has that title, at that company, in that location.

## Filling a row

| Column | How |
| --- | --- |
| `date_added` | Today, YYYY-MM-DD |
| `bde_id`, `task_id` | From your task message |
| `startup`, `territory`, `persona` | From your task, using the dropdowns |
| `first_name`, `last_name` | As on the profile |
| `title` | Copy the **current** title exactly |
| `company`, `company_domain` | Current company and its website (e.g. `acme.com`) |
| `company_size` | The headcount band from the company's LinkedIn page |
| `industry` | From the company's LinkedIn page |
| `city`, `state` | Where the person is based |
| `linkedin_url` | Public profile URL |
| `signal_notes` | Optional but valuable: a recent post, new job, hiring, a launch, a talk. One sentence. |

**Leave the grey columns alone** (`check_status` to `status_updated`). The agent and founders fill them in.

## Rows that get rejected, and how to avoid it

| Reason | Fix |
| --- | --- |
| Duplicate | Search the sheet (Ctrl+F) for the person or URL before adding |
| Title doesn't fit | Check seniority: "Security Analyst" is not a CISO |
| Outside territory | The person must be based in today's region |
| Company size | Check the company page's headcount band |
| Do-not-contact | Check the `DoNotContact` tab |
| Sales Navigator link | Use the public `linkedin.com/in/...` URL |

To fix a rejected row, correct it and clear its `check_status` cell. It will be checked again tonight.

## Rules

- Use your own LinkedIn account only. Never log in to anyone else's account.
- Don't message or connect with prospects.
- Don't collect personal emails or phone numbers.
- If you're unsure whether someone fits, skip them or note why in `signal_notes`.
