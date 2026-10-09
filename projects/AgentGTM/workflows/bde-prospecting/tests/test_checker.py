import pytest

from bde_prospecting import sheet
from bde_prospecting.checker import Checker, match_title, normalize_linkedin, normalize_state, summarize_by_bde


@pytest.mark.parametrize("url,expected", [
    ("https://www.linkedin.com/in/Jordan-Blake/", "https://www.linkedin.com/in/jordan-blake"),
    ("linkedin.com/in/jordan-blake?utm_source=share", "https://www.linkedin.com/in/jordan-blake"),
    ("http://in.linkedin.com/in/jordan-blake", "https://www.linkedin.com/in/jordan-blake"),
    ("https://www.linkedin.com/sales/lead/ACwAAA123,NAME", None),
    ("https://www.linkedin.com/company/granite", None),
    ("jordan blake", None),
])
def test_normalize_linkedin(url, expected):
    assert normalize_linkedin(url) == expected


def test_normalize_state():
    assert normalize_state("ny") == "NY"
    assert normalize_state("Massachusetts") == "MA"
    assert normalize_state("Ontario") is None


def check_one(cfg, row, others=(), dnc=()):
    rows = [*others, row]
    return Checker(cfg, use_llm=False).check(rows, list(dnc))[row["_row"]]


def test_valid_row_gets_score_and_new_status(cfg, make_row):
    upd = check_one(cfg, make_row(signal_notes="Spoke about GenAI data leakage at a meetup"))
    assert upd["check_status"] == sheet.VALID
    assert upd["status"] == sheet.NEW
    assert int(upd["score"]) >= 80


def test_missing_fields_rejected(cfg, make_row):
    upd = check_one(cfg, make_row(title="", linkedin_url=""))
    assert upd["check_status"] == sheet.REJECTED
    assert "missing title, linkedin_url" in upd["check_reasons"]


def test_sales_navigator_link_gets_specific_reason(cfg, make_row):
    upd = check_one(cfg, make_row(linkedin_url="https://www.linkedin.com/sales/lead/ACw123,NAME"))
    assert "Sales Navigator link" in upd["check_reasons"]


def test_duplicate_url_across_startups(cfg, make_row):
    first = make_row(check_status=sheet.VALID, linkedin_url="https://www.linkedin.com/in/x")
    dup = make_row(startup="autonomops", persona="midsize_cto", territory="northeast", company_size="201-500", linkedin_url="linkedin.com/in/X/")
    upd = check_one(cfg, dup, others=[first])
    assert upd["check_status"] == sheet.REJECTED
    assert f"duplicate of row {first['_row']}" in upd["check_reasons"]


def test_rejected_row_does_not_block_a_corrected_resubmission(cfg, make_row):
    bad = make_row(check_status=sheet.REJECTED, linkedin_url="https://www.linkedin.com/in/x")
    fixed = make_row(linkedin_url="https://www.linkedin.com/in/x")
    assert check_one(cfg, fixed, others=[bad])["check_status"] == sheet.VALID


def test_same_person_same_company_is_duplicate(cfg, make_row):
    first = make_row(check_status=sheet.VALID, linkedin_url="https://www.linkedin.com/in/a")
    again = make_row(linkedin_url="https://www.linkedin.com/in/b")
    assert "same person and company" in check_one(cfg, again, others=[first])["check_reasons"]


def test_do_not_contact_by_domain(cfg, make_row):
    dnc = [{"linkedin_url": "", "company_domain": "https://www.GraniteTrust.example/", "company": "", "reason": "customer", "added_by": "", "date": ""}]
    assert "do-not-contact" in check_one(cfg, make_row(), dnc=dnc)["check_reasons"]


def test_outside_territory(cfg, make_row):
    upd = check_one(cfg, make_row(city="Chicago", state="IL"))
    assert "IL is outside territory northeast" in upd["check_reasons"]


def test_company_size_outside_persona(cfg, make_row):
    upd = check_one(cfg, make_row(company_size="11-50"))
    assert "company size 11-50" in upd["check_reasons"]


def test_wrong_persona_for_startup(cfg, make_row):
    upd = check_one(cfg, make_row(persona="saas_cto"))
    assert "not one of daxa's personas" in upd["check_reasons"]


def test_junior_title_rejected(cfg, make_row):
    upd = check_one(cfg, make_row(title="Security Analyst"))
    assert upd["check_status"] == sheet.REJECTED


def test_unclear_title_goes_to_review_without_llm(cfg, make_row):
    upd = check_one(cfg, make_row(startup="autonomops", persona="sre_leader", territory="bay_area", state="CA", company_size="501-1000", title="Site Reliability Engineer"))
    assert upd["check_status"] == sheet.NEEDS_REVIEW


def test_checked_rows_are_left_alone(cfg, make_row):
    done = make_row(check_status=sheet.VALID)
    assert Checker(cfg, use_llm=False).check([done], []) == {}


def test_title_matching_uses_word_boundaries(cfg):
    cto = cfg.playbooks["fastn"].personas["saas_cto"]
    assert match_title("Director of Engineering", cto) == "unclear"  # "cto" inside "director" must not match
    assert match_title("Co-founder & CTO", cto) == "match"
    assert match_title("Technical Recruiter", cto) == "no_match"  # "recruit*" stem
    ciso = cfg.playbooks["daxa"].personas["ciso"]
    assert match_title("Head of Security, International", ciso) == "match"  # "intern" is not a stem


def test_summarize_by_bde(cfg, make_row):
    rows = [
        make_row(check_status=sheet.VALID),
        make_row(check_status=sheet.REJECTED, check_reasons="duplicate of row 2; IL is outside territory northeast"),
        make_row(check_status=sheet.REJECTED, check_reasons="duplicate of row 3"),
        make_row(),
    ]
    s = summarize_by_bde(rows)["BDE-01"]
    assert (s["checked"], s[sheet.VALID], s[sheet.REJECTED]) == (3, 1, 2)
    assert s["reasons"].most_common(1)[0] == ("duplicate", 2)


def test_contract_matches_sheet_columns():
    import json
    from bde_prospecting.config import PROJECT_DIR

    schema = json.loads((PROJECT_DIR / "contracts" / "prospect.v1.schema.json").read_text())
    assert list(schema["properties"]) == sheet.PROSPECT_COLUMNS
    assert schema["required"] == sheet.REQUIRED
