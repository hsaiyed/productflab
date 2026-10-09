from datetime import date

from bde_prospecting import planner, sheet

DAY = date(2026, 10, 13)


def test_one_task_per_bde_for_their_startups(cfg):
    plan = planner.plan_day(cfg, [], [], DAY)
    assert {t.bde_id for t in plan} == set(cfg.bdes)
    for t in plan:
        assert t.startup in cfg.bdes[t.bde_id].startups
        assert t.persona in cfg.playbooks[t.startup].personas
        assert cfg.playbooks[t.startup].territory_weights[t.territory] > 0


def test_mode_follows_linkedin_plan(cfg):
    for t in planner.plan_day(cfg, [], [], DAY):
        expected = "sales_navigator" if cfg.bdes[t.bde_id].linkedin_plan == "sales_navigator" else "google_xray"
        assert t.mode == expected


def test_deterministic(cfg):
    assert planner.plan_day(cfg, [], [], DAY) == planner.plan_day(cfg, [], [], DAY)


def test_does_not_plan_twice(cfg):
    tasks = [t.as_row() for t in planner.plan_day(cfg, [], [], DAY)]
    assert planner.plan_day(cfg, [], tasks, DAY) == []


def test_rotates_away_from_recent_assignments(cfg):
    day1 = planner.plan_day(cfg, [], [], DAY)
    tasks = [t.as_row() for t in day1]
    tasks = [dict(t, date="2026-10-12") for t in tasks]
    day2 = planner.plan_day(cfg, [], tasks, DAY)
    by_bde = {t.bde_id: (t.persona, t.territory) for t in day1}
    changed = [t for t in day2 if (t.persona, t.territory) != by_bde[t.bde_id]]
    assert changed, "at least one BDE should move to a different persona or territory"


def test_poor_acceptance_lowers_weight(cfg, make_row):
    good = planner.plan_day(cfg, [], [], DAY)
    top = next(t for t in good if t.bde_id == "BDE-01")
    rows = [make_row(startup=top.startup, persona=top.persona, territory=top.territory, check_status=sheet.VALID, status=sheet.INVITED) for _ in range(30)]
    after = next(t for t in planner.plan_day(cfg, rows, [], DAY) if t.bde_id == "BDE-01")
    assert (after.persona, after.territory) != (top.persona, top.territory) or after.weight < top.weight
