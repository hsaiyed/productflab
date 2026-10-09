"""Drive the real agent loop with a scripted model (no API key), to test the harness:
tool execution, refusals reaching the model, the completion nudge, audit trail and transcript."""

import json
import shutil
from datetime import date

import anthropic
import httpx2 as httpx

from bde_prospecting import sheet
from bde_prospecting.agent import run_agent
from bde_prospecting.config import WORKFLOW_DIR
from bde_prospecting.store import CsvStore
from bde_prospecting.tools import Toolbox

DAY = date(2026, 10, 12)
# Demo sheet rows: 8 Riley Grant (Security Analyst, rule-rejected), 14 Jamie Fox (unclear title)
RILEY, JAMIE = 8, 14


def tool(name, **inp):
    return {"type": "tool_use", "id": f"tu_{name}_{len(json.dumps(inp))}", "name": name, "input": inp}


def reply(*blocks, stop="tool_use"):
    return {"id": "msg", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": list(blocks),
            "stop_reason": stop, "stop_sequence": None, "usage": {"input_tokens": 100, "output_tokens": 20}}


SCRIPT = [
    reply(tool("get_situation")),
    reply(tool("get_rows_to_check")),
    # Tries to override a rule rejection (refused) and sends the unclear title to a human.
    reply(tool("record_check_decisions", decisions=[
        {"row": RILEY, "status": "valid", "reason": "looks senior"},
        {"row": JAMIE, "status": "needs_review", "reason": "'Reliability Lead' may be an IC role"},
    ])),
    reply(tool("apply_rule_results")),
    reply(tool("get_founder_candidates", startup="daxa")),
    # A note with a link is refused, so nothing is queued...
    reply(tool("queue_founder_invites", startup="daxa", invites=[{"row": 6, "note": "Hi Jordan, see https://daxa.ai"}])),
    # ...and the corrected call succeeds.
    reply(tool("queue_founder_invites", startup="daxa", invites=[
        {"row": 6, "note": "Hi Jordan, saw your talk on GenAI data leakage at the bank security meetup. Building in that space and would value connecting."},
    ], message_to_founder="Jordan spoke publicly about GenAI data leakage, a strong fit.")),
    reply(tool("write_journal", note="Queued 1 Daxa invite. Watch BDE-01 territory mistakes.")),
    reply({"type": "text", "text": "Checked rows; queued Daxa."}, stop="end_turn"),
    # After the completion nudge (other founders not queued), it escalates and finishes.
    reply(tool("escalate_to_human", question="Other founders' batches skipped in this test run.", urgency="low")),
    reply({"type": "text", "text": "Done. One escalation for you."}, stop="end_turn"),
]


def test_agent_loop_with_scripted_model(tmp_path, cfg, monkeypatch):
    shutil.copytree(WORKFLOW_DIR / "examples" / "demo-sheet", tmp_path / "sheet")
    store = CsvStore(tmp_path / "sheet")
    requests, script = [], iter(SCRIPT)

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=next(script))

    client = anthropic.Anthropic(api_key="test", http_client=anthropic.DefaultHttpxClient(transport=httpx.MockTransport(handler)))
    toolbox = Toolbox(cfg, store, DAY, "evening", outbox=tmp_path / "outbox")
    result = run_agent(toolbox, client=client)

    # The loop ran the whole script, including the nudge.
    assert len(requests) == len(SCRIPT)
    assert result["nudged"] is True
    assert result["summary"] == "Done. One escalation for you."

    # Least privilege: evening tools only.
    names = {t["name"] for t in requests[0]["tools"]}
    assert "assign_task" not in names and "queue_founder_invites" in names
    assert requests[0]["fallbacks"] == "default"

    # Refusals reached the model as error results.
    def tool_results(req):
        return [b for m in req["messages"] if m["role"] == "user" and isinstance(m["content"], list) for b in m["content"] if b.get("type") == "tool_result"]
    after_decisions = tool_results(requests[3])[-1]
    assert "rules rejected it" in json.dumps(after_decisions)
    after_bad_note = tool_results(requests[6])[-1]
    assert after_bad_note.get("is_error") is True and "contains a link" in json.dumps(after_bad_note)
    assert "still open" in json.dumps(requests[9]["messages"][-1])

    # End state in the sheet.
    rows = {r["_row"]: r for r in store.read_prospects()}
    assert rows[RILEY]["check_status"] == sheet.REJECTED
    assert rows[JAMIE]["check_status"] == sheet.NEEDS_REVIEW
    assert rows[6]["status"] == sheet.QUEUED and "GenAI" in rows[6]["founder_note"]
    assert store.read_agent_log()[-1]["note"].startswith("Queued 1 Daxa invite")

    # Audit trail, owner message and transcript.
    kinds = [a["action"] for a in result["actions"]]
    assert "queue_founder_invites" in kinds and "escalate" in kinds and "journal" in kinds
    assert (tmp_path / "outbox" / "2026-10-12" / "owner-review.md").exists()
    assert (tmp_path / "outbox" / "2026-10-12" / "founder-daxa.md").read_text().startswith("# Daxa")
    assert (tmp_path / "outbox" / "2026-10-12" / "agent-evening-transcript.json").exists()
