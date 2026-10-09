import shutil

from bde_prospecting import cli, sheet
from bde_prospecting.config import WORKFLOW_DIR
from bde_prospecting.store import CsvStore


def test_full_day_on_demo_sheet(tmp_path):
    shutil.copytree(WORKFLOW_DIR / "examples" / "demo-sheet", tmp_path / "sheet")
    base = ["--store", f"csv:{tmp_path / 'sheet'}", "--outbox", str(tmp_path / "outbox"), "--no-llm", "--date"]
    cli.main(["check", *base, "2026-10-12"])
    cli.main(["founder-batch", *base, "2026-10-12"])
    cli.main(["plan", *base, "2026-10-13"])
    cli.main(["weekly-report", *base, "2026-10-13"])

    rows = CsvStore(tmp_path / "sheet").read_prospects()
    assert all(r["check_status"] for r in rows), "every row should be checked"
    by_name = {f"{r['first_name']} {r['last_name']}": r for r in rows if r["date_added"] == "2026-10-12"}
    assert by_name["Jordan Blake"]["status"] == sheet.QUEUED
    assert by_name["Riley Grant"]["check_status"] == sheet.REJECTED  # Security Analyst
    assert by_name["Chris Nolan"]["check_status"] == sheet.REJECTED  # do-not-contact
    assert by_name["Jamie Fox"]["check_status"] == sheet.NEEDS_REVIEW

    outbox = tmp_path / "outbox"
    assert (outbox / "2026-10-12" / "founder-daxa.md").exists()
    assert (outbox / "2026-10-12" / "owner-review.md").exists()
    for bde in ("BDE-01", "BDE-02", "BDE-03", "BDE-04"):
        text = (outbox / "2026-10-13" / f"{bde}.md").read_text()
        assert "Yesterday's results" in text
    assert "## BDE quality" in (outbox / "2026-10-13" / "weekly-report.md").read_text()

    # Re-running is safe: nothing is re-checked, re-queued or re-planned.
    before = CsvStore(tmp_path / "sheet").read_prospects()
    cli.main(["check", *base, "2026-10-12"])
    cli.main(["plan", *base, "2026-10-13"])
    assert CsvStore(tmp_path / "sheet").read_prospects() == before
    assert len(CsvStore(tmp_path / "sheet").read_tasks()) == 8
