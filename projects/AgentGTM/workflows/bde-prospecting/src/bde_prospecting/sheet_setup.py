"""One-time Google Sheet setup: tabs, headers, dropdowns, and protection on agent columns."""

from . import sheet
from .config import COMPANY_SIZES


def _dropdown(sheet_id, col_index, values):
    return {
        "setDataValidation": {
            "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": col_index, "endColumnIndex": col_index + 1},
            "rule": {
                "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in values]},
                "strict": True,
                "showCustomUi": True,
            },
        }
    }


def setup_spreadsheet(book, cfg):
    existing = {ws.title: ws for ws in book.worksheets()}
    layouts = {
        sheet.PROSPECTS: sheet.PROSPECT_COLUMNS,
        sheet.TASKS: sheet.TASK_COLUMNS,
        sheet.DO_NOT_CONTACT: sheet.DNC_COLUMNS,
    }
    for title, columns in layouts.items():
        ws = existing.get(title) or book.add_worksheet(title=title, rows=2000, cols=len(columns))
        if ws.row_values(1) != columns:
            ws.update([columns], "A1")
        ws.freeze(rows=1)
        existing[title] = ws

    prospects = existing[sheet.PROSPECTS]
    cols = sheet.PROSPECT_COLUMNS
    personas = sorted({p for pb in cfg.playbooks.values() for p in pb.personas})
    dropdowns = {
        "bde_id": sorted(cfg.bdes),
        "startup": sorted(cfg.playbooks),
        "territory": sorted(cfg.territories),
        "persona": personas,
        "company_size": COMPANY_SIZES,
        "status": sheet.STATUSES,
    }
    requests = [_dropdown(prospects.id, cols.index(c), v) for c, v in dropdowns.items()]

    # Grey background on the agent's columns so BDEs know to leave them alone.
    first_agent = cols.index(sheet.AGENT_COLUMNS[0])
    requests.append({
        "repeatCell": {
            "range": {"sheetId": prospects.id, "startColumnIndex": first_agent, "endColumnIndex": len(cols)},
            "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.93, "green": 0.93, "blue": 0.93}}},
            "fields": "userEnteredFormat.backgroundColor",
        }
    })

    # Agent-owned columns (except status, which founders update) warn before anyone edits them.
    already_protected = bool(book.list_protected_ranges(prospects.id))
    protected = [] if already_protected else [c for c in sheet.AGENT_COLUMNS if c != "status"]
    for c in protected:
        i = cols.index(c)
        requests.append({
            "addProtectedRange": {
                "protectedRange": {
                    "range": {"sheetId": prospects.id, "startColumnIndex": i, "endColumnIndex": i + 1},
                    "description": f"{c} is filled in by the agent",
                    "warningOnly": True,
                }
            }
        })
    book.batch_update({"requests": requests})
