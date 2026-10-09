"""AgentGTM web app: founders' invite pages and the owner dashboard, behind Google sign-in.

Run locally:   streamlit run app/streamlit_app.py
Config:        AGENTGTM_STORE=sheets:<id> (or csv:<dir>), .streamlit/secrets.toml with [auth] for Google.
Access rules:  src/bde_prospecting/access.py (checked on the server for every action).
"""

import json
import os
from datetime import date

import streamlit as st

from bde_prospecting import access, llm, sheet
from bde_prospecting.checker import normalize_linkedin
from bde_prospecting.config import load_config
from bde_prospecting.store import open_store
from bde_prospecting.tools import Toolbox

st.set_page_config(page_title="AgentGTM", page_icon="📈", layout="wide")

STORE_SPEC = os.environ.get("AGENTGTM_STORE", "")
IS_CSV = STORE_SPEC.startswith("csv:")


@st.cache_resource
def get_cfg():
    return load_config()


@st.cache_resource
def get_store():
    return open_store(STORE_SPEC)


@st.cache_data(ttl=60, show_spinner=False)
def load_rows():
    return get_store().read_prospects()


@st.cache_data(ttl=60, show_spinner=False)
def load_agent_log():
    return get_store().read_agent_log()


def refresh():
    load_rows.clear()
    load_agent_log.clear()


def today():
    # A fixed date is only for demos and tests on CSV data.
    if IS_CSV and os.environ.get("AGENTGTM_TODAY"):
        return date.fromisoformat(os.environ["AGENTGTM_TODAY"])
    return date.today()


# ---------------- sign-in ----------------

def signed_in_email():
    """Return (email, verified) for the signed-in Google account, or stop with the sign-in page."""
    dev_email = os.environ.get("AGENTGTM_DEV_LOGIN_EMAIL")
    if dev_email:
        if not IS_CSV:
            st.error("AGENTGTM_DEV_LOGIN_EMAIL is only allowed with a csv: store. Remove it in production.")
            st.stop()
        return dev_email, True
    if not st.user.is_logged_in:
        st.title("AgentGTM")
        st.write("Sign in with the Google account your invite was sent to.")
        st.button("Sign in with Google", on_click=st.login, args=["google"], type="primary")
        st.stop()
    return st.user.get("email"), bool(st.user.get("email_verified", False))


def sidebar(viewer):
    with st.sidebar:
        st.caption("Signed in as")
        st.write(viewer.email)
        st.caption("Owner" if viewer.is_owner else "Founder: " + ", ".join(get_cfg().playbooks[s].name for s in viewer.startups))
        if st.button("Refresh data"):
            refresh()
            st.rerun()
        if not os.environ.get("AGENTGTM_DEV_LOGIN_EMAIL"):
            st.button("Sign out", on_click=st.logout)


# ---------------- founder page ----------------

def act(viewer, row, new_status):
    try:
        access.update_status(viewer, get_cfg(), get_store(), row["_row"], new_status, today().isoformat())
        st.toast(f"{row['first_name']} {row['last_name']}: {access.LABELS[new_status]}")
    except access.AccessDenied as e:
        st.error(str(e))
    refresh()


def prospect_card(viewer, row, show_note):
    cfg = get_cfg()
    pb = cfg.playbooks[row["startup"]]
    persona = pb.personas.get(row["persona"])
    with st.container(border=True):
        left, right = st.columns([3, 2])
        with left:
            st.markdown(f"**{_md(row['first_name'])} {_md(row['last_name'])}**")
            st.text(f"{row['title']} at {row['company']}\n{row['city']}, {row['state']}")
            if persona:
                st.caption(f"Persona: {persona.label}" + (f" · score {row['score']}" if row["score"] else ""))
            if row["signal_notes"]:
                st.caption("Why now")
                st.text(row["signal_notes"])
        with right:
            if show_note and row["founder_note"]:
                st.caption("Connection note (copy with the icon)")
                st.code(row["founder_note"], language=None, wrap_lines=True)
            url = normalize_linkedin(row["linkedin_url"])
            if url:
                st.link_button("Open LinkedIn profile", url)
            buttons = access.allowed_next(row["status"])
            if buttons:
                cols = st.columns(len(buttons))
                for col, status in zip(cols, buttons):
                    col.button(access.LABELS[status], key=f"{row['_row']}-{status}", on_click=act, args=(viewer, row, status),
                               type="primary" if status == (access.TRANSITIONS.get(row["status"]) or [None])[0] else "secondary")


def _md(text):
    """Escape markdown in names typed by BDEs."""
    return "".join("\\" + c if c in "\\`*_{}[]()#+-.!|<>~" else c for c in text)


def founder_page(viewer, startup):
    cfg = get_cfg()
    pb = cfg.playbooks[startup]
    rows = [r for r in load_rows() if r["startup"] == startup and r["check_status"] == sheet.VALID]
    stages = {
        "Today's invites": [r for r in rows if r["status"] == sheet.QUEUED],
        "Waiting to accept": [r for r in rows if r["status"] == sheet.INVITED],
        "Connected": [r for r in rows if r["status"] in (sheet.ACCEPTED, sheet.REPLIED)],
        "Meetings": [r for r in rows if r["status"] == sheet.MEETING],
    }
    st.header(pb.name)
    st.caption(pb.one_liner)
    m = st.columns(4)
    for col, (label, items) in zip(m, stages.items()):
        col.metric(label, len(items))
    sent = sum(1 for r in rows if r["status"] in sheet.SENT_STAGES)
    accepted = sum(1 for r in rows if r["status"] in sheet.ACCEPTED_STAGES)
    if sent:
        st.caption(f"Acceptance so far: {accepted}/{sent} ({accepted / sent:.0%})")

    tabs = st.tabs([f"{label} ({len(items)})" for label, items in stages.items()])
    hints = {
        "Today's invites": "Send each invite from your own LinkedIn with the note, then press **Sent invite**.",
        "Waiting to accept": "Press **Accepted** when they accept. The note works as a first message if your account can't attach notes.",
        "Connected": "Follow up in LinkedIn messages. Record replies and meetings here so the agent learns what works.",
        "Meetings": "Great work.",
    }
    for tab, (label, items) in zip(tabs, stages.items()):
        with tab:
            st.info(hints[label])
            if not items:
                st.write("Nothing here right now.")
            for row in sorted(items, key=lambda r: (-int(r["score"] or 0), r["_row"])):
                prospect_card(viewer, row, show_note=label in ("Today's invites", "Waiting to accept"))


# ---------------- owner dashboard ----------------

def owner_dashboard(viewer):
    cfg, store = get_cfg(), get_store()
    rows = load_rows()
    tb = Toolbox(cfg, store, today(), "ask")
    st.header("Owner dashboard")
    tabs = st.tabs(["Pipeline", "BDEs", f"Review queue ({sum(1 for r in rows if r['check_status'] == sheet.NEEDS_REVIEW)})",
                    "Agent activity", "Founder pages", "Ask the agent"])

    with tabs[0]:
        table = []
        for pb in cfg.playbooks.values():
            rs = [r for r in rows if r["startup"] == pb.id and r["check_status"] == sheet.VALID]
            sent = sum(1 for r in rs if r["status"] in sheet.SENT_STAGES)
            acc = sum(1 for r in rs if r["status"] in sheet.ACCEPTED_STAGES)
            table.append({
                "Startup": pb.name, "Valid prospects": len(rs),
                "Waiting for founder": sum(1 for r in rs if r["status"] == sheet.QUEUED),
                "Invited": sent, "Accepted": acc, "Meetings": sum(1 for r in rs if r["status"] == sheet.MEETING),
                "Acceptance": f"{acc / sent:.0%}" if sent else "—", "Playbook confirmed": "yes" if pb.confirmed else "no",
            })
        st.dataframe(table, hide_index=True, width="stretch")
        group = st.radio("Funnel by", ["persona", "territory", "bde"], horizontal=True)
        st.dataframe([{
            group.capitalize(): f[group], "Valid": f["valid"], "Invited": f["invited"], "Accepted": f["accepted"],
            "Replied": f["replied"], "Meetings": f["meetings"],
            "Acceptance": f"{f['acceptance_rate']:.0%}" if f["acceptance_rate"] is not None else "—",
        } for f in json.loads(tb.get_performance(group))["rows"]], hide_index=True, width="stretch")
        st.caption("Acceptance rates below ~10 invites are noise.")

    with tabs[1]:
        days = st.slider("Days", 1, 30, 7)
        hist = [json.loads(tb.get_bde_history(b, days)) for b in sorted(cfg.bdes)]
        st.dataframe([{
            "BDE": h["bde_id"], "Rows added": h["rows_added"], "Valid": h["valid"], "Rejected": h["rejected"],
            "Needs review": h["needs_review"],
            "Valid rate": f"{h['valid'] / (h['valid'] + h['rejected']):.0%}" if h["valid"] + h["rejected"] else "—",
            "Signal notes": f"{h['signal_notes_fill_rate']:.0%}" if h["signal_notes_fill_rate"] is not None else "—",
            "Invites accepted": f"{h['invites_accepted']}/{h['invites_sent_to_their_prospects']}",
            "Top mistake": h["top_rejection_reasons"][0][0] if h["top_rejection_reasons"] else "—",
        } for h in hist], hide_index=True, width="stretch")

    with tabs[2]:
        review = [r for r in rows if r["check_status"] == sheet.NEEDS_REVIEW]
        if not review:
            st.write("Nothing waiting for you.")
        for r in review:
            with st.container(border=True):
                st.markdown(f"**Row {r['_row']}** · {_md(r['bde_id'])} · {_md(r['startup'])} / {_md(r['persona'])}")
                st.text(f"{r['first_name']} {r['last_name']}, {r['title']} at {r['company']} ({r['city']}, {r['state']})")
                st.caption("Why it's here")
                st.text(r["check_reasons"])
                reason = st.text_input("Reason for the BDE (needed to reject)", key=f"reason-{r['_row']}")
                a, b, _ = st.columns([1, 1, 6])
                if a.button("Approve", key=f"approve-{r['_row']}", type="primary"):
                    _decide(viewer, r, sheet.VALID, "")
                if b.button("Reject", key=f"reject-{r['_row']}"):
                    _decide(viewer, r, sheet.REJECTED, reason)

    with tabs[3]:
        log = list(reversed(load_agent_log()))
        proposals = [e for e in log if e["mode"] == "weekly-proposals"]
        if proposals:
            st.subheader("Latest proposed changes (approve by editing the playbooks)")
            for line in proposals[0]["note"].splitlines():
                st.text(f"• {line}")
        st.subheader("Recent runs and notes")
        if not log:
            st.write("The agent hasn't run yet.")
        for e in log[:30]:
            with st.expander(f"{e['date']} · {e['mode']}"):
                st.text(e["note"])

    with tabs[4]:
        startup = st.selectbox("Startup", sorted(cfg.playbooks), format_func=lambda s: cfg.playbooks[s].name)
        founder_page(viewer, startup)

    with tabs[5]:
        if not llm.available():
            st.write("Set ANTHROPIC_API_KEY on the server to ask the agent questions.")
        else:
            question = st.text_area("Question", placeholder="Which BDE needs coaching most, and on what?")
            if st.button("Ask", type="primary") and question.strip():
                from bde_prospecting.agent import run_agent

                with st.spinner("The agent is looking at the data..."):
                    result = run_agent(Toolbox(cfg, store, today(), "ask"), question=question.strip())
                st.markdown(result["summary"] or "(no answer)")
                st.caption(f"{result['usage']['turns']} turns · {result['seconds']}s")


def _decide(viewer, row, decision, reason):
    try:
        access.decide_review(viewer, get_cfg(), get_store(), row["_row"], decision, reason, today().isoformat())
        st.toast(f"Row {row['_row']}: {decision}")
        refresh()
        st.rerun()
    except access.AccessDenied as e:
        st.error(str(e))


# ---------------- main ----------------

def main():
    if not STORE_SPEC:
        st.error("Set AGENTGTM_STORE to sheets:<spreadsheet id>.")
        st.stop()
    email, verified = signed_in_email()
    viewer = access.resolve_viewer(get_cfg(), email, verified)
    if viewer is None:
        st.title("AgentGTM")
        st.warning(f"{email} doesn't have access. Ask the owner to add this Google account.")
        if not os.environ.get("AGENTGTM_DEV_LOGIN_EMAIL"):
            st.button("Sign out", on_click=st.logout)
        st.stop()
    sidebar(viewer)
    if viewer.is_owner:
        owner_dashboard(viewer)
    elif len(viewer.startups) == 1:
        founder_page(viewer, viewer.startups[0])
    else:
        cfg = get_cfg()
        startup = st.sidebar.selectbox("Startup", viewer.startups, format_func=lambda s: cfg.playbooks[s].name)
        founder_page(viewer, startup)


main()
