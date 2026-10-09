from bde_prospecting import founder, llm, sheet


def test_template_note_passes_guardrails(cfg, make_row):
    row = make_row()
    note = founder.template_note(row, cfg.playbooks["daxa"])
    assert founder.note_problems(note, row) == []
    assert "security" in note


def test_guardrails_catch_bad_notes(make_row):
    row = make_row()
    assert "contains a link" in founder.note_problems("Hi Jordan, see https://x.example", row)
    assert "contains a placeholder" in founder.note_problems("Hi Jordan, loved your post on {topic}", row)
    assert "doesn't use the person's first name" in founder.note_problems("Hi there, glad to connect.", row)
    assert any("characters" in p for p in founder.note_problems("Hi Jordan " + "x" * llm.NOTE_LIMIT, row))


def test_picks_only_new_valid_rows_highest_score_first(cfg, make_row):
    pb = cfg.playbooks["daxa"]
    rows = [
        make_row(check_status=sheet.VALID, status=sheet.NEW, score="60", first_name="Low"),
        make_row(check_status=sheet.VALID, status=sheet.NEW, score="90", first_name="High"),
        make_row(check_status=sheet.VALID, status=sheet.INVITED, score="99", first_name="Done"),
        make_row(check_status=sheet.REJECTED, score="", first_name="Bad"),
        make_row(check_status=sheet.VALID, status=sheet.NEW, startup="fastn", persona="saas_cto", score="99", first_name="Other"),
    ]
    picks = founder.pick_and_draft(cfg, pb, rows, use_llm=False)
    assert [r["first_name"] for r, _, _ in picks] == ["High", "Low"]
    assert all(src == "template" for *_, src in picks)


def test_respects_daily_limit(cfg, make_row):
    pb = cfg.playbooks["daxa"]
    rows = [make_row(check_status=sheet.VALID, status=sheet.NEW, linkedin_url=f"https://www.linkedin.com/in/p{i}") for i in range(pb.daily_invites + 5)]
    assert len(founder.pick_and_draft(cfg, pb, rows, use_llm=False)) == pb.daily_invites
