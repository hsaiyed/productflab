"""Drive the web app as different signed-in users (dev sign-in on CSV data; Google sign-in is Streamlit's)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from bde_prospecting import access, sheet
from bde_prospecting.config import WORKFLOW_DIR, load_config
from bde_prospecting.store import CsvStore

APP = str(WORKFLOW_DIR / "app" / "streamlit_app.py")


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """The same prepared demo data app/demo.py uses (rows checked, invites queued)."""
    sys.path.insert(0, str(WORKFLOW_DIR / "app"))
    import demo as demo_mod

    return demo_mod.prepare()


@pytest.fixture
def app(demo, monkeypatch):
    def make(email):
        monkeypatch.setenv("AGENTGTM_STORE", f"csv:{demo / 'sheet'}")
        monkeypatch.setenv("AGENTGTM_CONFIG_DIR", str(demo / "config"))
        monkeypatch.setenv("AGENTGTM_PLAYBOOK_DIR", str(demo / "playbooks"))
        monkeypatch.setenv("AGENTGTM_DEV_LOGIN_EMAIL", email)
        monkeypatch.setenv("AGENTGTM_TODAY", "2026-10-12")
        st.cache_resource.clear()
        st.cache_data.clear()
        at = AppTest.from_file(APP, default_timeout=30)
        at.run()
        assert not at.exception, at.exception
        return at
    return make


def texts(at):
    return " ".join([e.value for e in at.markdown] + [e.value for e in at.text] + [e.value for e in at.header] + [str(e.value) for e in at.caption])


def test_stranger_has_no_access(app):
    at = app("someone@else.example")
    assert "doesn't have access" in at.warning[0].value
    assert not at.tabs


def test_founder_sees_only_their_startup(app):
    at = app("founder@daxa.demo.example")
    body = texts(at)
    assert "Daxa" in body and "Jordan" in body
    assert "Drew" not in body and "Robin" not in body  # other startups' prospects
    assert "Owner dashboard" not in body


def test_founder_marks_invite_sent(app, demo):
    at = app("founder@daxa.demo.example")
    store = CsvStore(demo / "sheet")
    row = next(r for r in store.read_prospects() if r["first_name"] == "Jordan")
    assert row["status"] == sheet.QUEUED
    at.button(key=f"{row['_row']}-{sheet.INVITED}").click().run()
    assert not at.exception
    assert {r["_row"]: r for r in store.read_prospects()}[row["_row"]]["status"] == sheet.INVITED


def test_owner_sees_dashboard_and_review_queue(app):
    at = app("owner@demo.example")
    body = texts(at)
    assert "Owner dashboard" in body
    assert any("Review queue" in t.label for t in at.tabs)
    assert "Reliability Lead" in body  # the row waiting for review


def test_founder_cannot_change_another_startups_row(demo):
    cfg = load_config(demo / "config", demo / "playbooks")
    store = CsvStore(demo / "sheet")
    viewer = access.resolve_viewer(cfg, "founder@daxa.demo.example")
    other = next(r for r in store.read_prospects() if r["startup"] == "fastn" and r["status"] == sheet.QUEUED)
    with pytest.raises(access.AccessDenied, match="another startup"):
        access.update_status(viewer, cfg, store, other["_row"], sheet.INVITED, "2026-10-12")
    with pytest.raises(access.AccessDenied, match="only the owner"):
        access.decide_review(viewer, cfg, store, other["_row"], sheet.VALID, "", "2026-10-12")


def test_unverified_or_unknown_email_rejected(demo):
    cfg = load_config(demo / "config", demo / "playbooks")
    assert access.resolve_viewer(cfg, "founder@daxa.demo.example", email_verified=False) is None
    assert access.resolve_viewer(cfg, "Founder@Daxa.Demo.Example").startups == ("daxa",)  # case-insensitive
    assert access.resolve_viewer(cfg, "owner@demo.example").is_owner


def test_status_transitions(demo):
    cfg = load_config(demo / "config", demo / "playbooks")
    store = CsvStore(demo / "sheet")
    owner = access.resolve_viewer(cfg, "owner@demo.example")
    row = next(r for r in store.read_prospects() if r["status"] == sheet.QUEUED)
    with pytest.raises(access.AccessDenied, match="can't move"):
        access.update_status(owner, cfg, store, row["_row"], sheet.MEETING, "2026-10-12")
    access.update_status(owner, cfg, store, row["_row"], sheet.DNC, "2026-10-12")
    assert any(d["linkedin_url"] == row["linkedin_url"] for d in store.read_do_not_contact())


def test_dev_login_refused_with_google_sheet(monkeypatch):
    monkeypatch.setenv("AGENTGTM_STORE", "sheets:abc")
    monkeypatch.setenv("AGENTGTM_DEV_LOGIN_EMAIL", "owner@demo.example")
    st.cache_resource.clear()
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert "only allowed with a csv: store" in at.error[0].value
