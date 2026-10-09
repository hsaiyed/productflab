"""Run the web app locally on the demo sheet, signed in as a demo user (no Google setup needed).

    python app/demo.py owner          # owner dashboard
    python app/demo.py daxa           # Daxa founder page
    python app/demo.py stranger       # someone without access

Copies the demo sheet and config to a temp folder and adds demo sign-in emails there.
Never use AGENTGTM_DEV_LOGIN_EMAIL in production; the app refuses it with a Google Sheet.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1]
PROJECT = WORKFLOW.parents[1]
OWNER = "owner@demo.example"


def prepare():
    tmp = Path(tempfile.mkdtemp(prefix="agentgtm-app-demo-"))
    shutil.copytree(WORKFLOW / "examples" / "demo-sheet", tmp / "sheet")
    shutil.copytree(WORKFLOW / "config", tmp / "config")
    shutil.copytree(PROJECT / "playbooks", tmp / "playbooks")
    roster = tmp / "config" / "bdes.toml"
    roster.write_text(roster.read_text().replace("emails = []", f'emails = ["{OWNER}"]', 1))
    for pb in (tmp / "playbooks").glob("*.toml"):
        pb.write_text(pb.read_text().replace("founder_emails = []", f'founder_emails = ["founder@{pb.stem}.demo.example"]', 1))
    # Queue a few invites and give some history so every page has something to show.
    sys.path.insert(0, str(WORKFLOW / "src"))
    from datetime import date

    from bde_prospecting.config import load_config
    from bde_prospecting.store import CsvStore
    from bde_prospecting.tools import Toolbox

    cfg = load_config(tmp / "config", tmp / "playbooks")
    tb = Toolbox(cfg, CsvStore(tmp / "sheet"), date(2026, 10, 12), "evening", outbox=tmp / "outbox")
    import json

    tb.get_rows_to_check()
    left = json.loads(tb.apply_rule_results())["rows_still_needing_your_decision"]
    if left:
        tb.escalate_to_human("Title fit unclear: is 'Reliability Lead, Payments' an SRE leader?", rows=left)
    for pb in cfg.playbooks.values():
        cands = json.loads(tb.get_founder_candidates(pb.id))["candidates"]
        invites = [{"row": c["row"], "note": json.loads(tb.draft_invite_note(c["row"]))["note"]} for c in cands]
        if invites:
            tb.queue_founder_invites(pb.id, invites)
    tb.write_journal("Demo: checked 16 rows, queued invites for all four founders. Watch BDE-01 territory mistakes.")
    return tmp


def main():
    who = sys.argv[1] if len(sys.argv) > 1 else "owner"
    email = {"owner": OWNER, "stranger": "someone@else.example"}.get(who, f"founder@{who}.demo.example")
    tmp = prepare()
    env = dict(os.environ, AGENTGTM_STORE=f"csv:{tmp / 'sheet'}", AGENTGTM_CONFIG_DIR=str(tmp / "config"),
               AGENTGTM_PLAYBOOK_DIR=str(tmp / "playbooks"), AGENTGTM_DEV_LOGIN_EMAIL=email, AGENTGTM_TODAY="2026-10-12",
               AGENTGTM_DISABLE_LLM=os.environ.get("AGENTGTM_DISABLE_LLM", "1"), PYTHONPATH=str(WORKFLOW / "src"),
               STREAMLIT_CLIENT_TOOLBAR_MODE="viewer", STREAMLIT_BROWSER_GATHER_USAGE_STATS="false")
    print(f"Signed in as {email}. Demo data in {tmp}")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(WORKFLOW / "app" / "streamlit_app.py"), *sys.argv[2:]], env=env, check=False)


if __name__ == "__main__":
    main()
