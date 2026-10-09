"""The rules the agent can't break are enforced in the tools; test them directly."""

import json
import shutil
from datetime import date

import pytest

from bde_prospecting import sheet
from bde_prospecting.config import WORKFLOW_DIR
from bde_prospecting.store import CsvStore
from bde_prospecting.tools import Toolbox, ToolRefused

DAY = date(2026, 10, 13)


@pytest.fixture
def tb(tmp_path, cfg):
    shutil.copytree(WORKFLOW_DIR / "examples" / "demo-sheet", tmp_path / "sheet")
    def make(mode, day=DAY):
        return Toolbox(cfg, CsvStore(tmp_path / "sheet"), day, mode, outbox=tmp_path / "outbox")
    return make


def test_assign_task_rules(tb):
    t = tb("morning")
    with pytest.raises(ToolRefused, match="works on"):
        t.assign_task("BDE-01", "fastn", "saas_cto", "bay_area", 20, "x")
    with pytest.raises(ToolRefused, match="not a daxa persona"):
        t.assign_task("BDE-01", "daxa", "saas_cto", "bay_area", 20, "x")
    with pytest.raises(ToolRefused, match="target must be"):
        t.assign_task("BDE-01", "daxa", "ciso", "bay_area", 500, "x")
    out = json.loads(t.assign_task("BDE-01", "daxa", "ciso", "bay_area", 30, "test", coach_note="Check the location."))
    assert out["ok"]
    with pytest.raises(ToolRefused, match="already has a task"):
        t.assign_task("BDE-01", "daxa", "ciso", "northeast", 30, "x")
    text = (t.outbox / "2026-10-13" / "BDE-01.md").read_text()
    assert "Check the location." in text


def test_assignment_options_are_ranked(tb):
    t = tb("morning")
    options = json.loads(t.get_assignment_options("BDE-01"))["options"]
    assert options == sorted(options, key=lambda o: -o["weight"])


def test_rule_rejected_row_cannot_be_made_valid(tb):
    t = tb("evening", date(2026, 10, 12))
    t.get_rows_to_check()
    out = json.loads(t.record_check_decisions([{"row": 8, "status": "valid", "reason": ""}]))
    assert out["recorded"] == 0 and "rules rejected it" in out["refused"][0]["why"]


def test_non_valid_decision_needs_reason(tb):
    t = tb("evening", date(2026, 10, 12))
    t.get_rows_to_check()
    out = json.loads(t.record_check_decisions([{"row": 14, "status": "rejected", "reason": " "}]))
    assert out["refused"][0]["why"] == "a reason is required"


def test_queue_respects_limit_eligibility_and_guardrails(tb, cfg):
    t = tb("evening", date(2026, 10, 12))
    t.get_rows_to_check()
    t.apply_rule_results()
    with pytest.raises(ToolRefused, match="not an eligible candidate"):
        t.queue_founder_invites("daxa", [{"row": 8, "note": "Hi Riley, glad to connect."}])
    with pytest.raises(ToolRefused, match="doesn't use the person's first name"):
        t.queue_founder_invites("daxa", [{"row": 6, "note": "Hello there, glad to connect."}])
    too_many = [{"row": 6, "note": "Hi Jordan"}] * (cfg.playbooks["daxa"].daily_invites + 1)
    with pytest.raises(ToolRefused, match="more invites allowed"):
        t.queue_founder_invites("daxa", too_many)
    assert json.loads(t.queue_founder_invites("daxa", [{"row": 6, "note": "Hi Jordan, glad to connect."}]))["ok"]
    with pytest.raises(ToolRefused, match="not an eligible candidate"):
        t.queue_founder_invites("daxa", [{"row": 6, "note": "Hi Jordan, glad to connect."}])  # already queued


def test_escalation_marks_rows_and_reaches_owner(tb):
    t = tb("evening", date(2026, 10, 12))
    t.get_rows_to_check()
    t.escalate_to_human("Is 'Reliability Lead, Payments' a leader?", rows=[14])
    assert t.deliver_escalations()
    assert {r["_row"]: r for r in t.store.read_prospects()}[14]["check_status"] == sheet.NEEDS_REVIEW
    assert "Reliability Lead" in (t.outbox / "2026-10-12" / "owner-review.md").read_text()


def test_least_privilege_by_mode(tb):
    names = {m: {f.__name__ for f in tb(m).tools_for(m)} for m in Toolbox.MODE_TOOLS}
    assert "assign_task" in names["morning"] and "assign_task" not in names["evening"]
    assert "queue_founder_invites" not in names["morning"]
    assert not names["ask"] & {"assign_task", "record_check_decisions", "queue_founder_invites", "escalate_to_human", "write_journal"}


def test_open_items(tb):
    t = tb("morning")
    assert any("without a task" in i for i in t.open_items())
