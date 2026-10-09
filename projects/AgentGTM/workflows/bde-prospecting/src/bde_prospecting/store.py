"""Where the prospect list lives: a Google Sheet in production, CSV files for demos and tests.

Both stores expose the same methods. Prospect rows are dicts keyed by column name,
plus "_row": the row's 1-based position in the sheet (header is row 1).
"""

import csv
import os
from pathlib import Path

from . import sheet


def open_store(spec):
    """spec is "csv:<directory>" or "sheets:<spreadsheet id>"."""
    kind, _, target = spec.partition(":")
    if kind == "csv" and target:
        return CsvStore(target)
    if kind == "sheets" and target:
        return SheetsStore(target)
    raise ValueError(f"unknown store {spec!r}; use csv:<dir> or sheets:<spreadsheet id>")


def _with_columns(record, columns):
    return {c: str(record.get(c, "") if record.get(c) is not None else "") for c in columns}


class CsvStore:
    FILES = {sheet.PROSPECTS: "prospects.csv", sheet.TASKS: "tasks.csv", sheet.DO_NOT_CONTACT: "do_not_contact.csv", sheet.AGENT_LOG: "agent_log.csv"}
    COLUMNS = {sheet.PROSPECTS: sheet.PROSPECT_COLUMNS, sheet.TASKS: sheet.TASK_COLUMNS, sheet.DO_NOT_CONTACT: sheet.DNC_COLUMNS, sheet.AGENT_LOG: sheet.AGENT_LOG_COLUMNS}

    def __init__(self, directory):
        self.dir = Path(directory)

    def setup(self, cfg=None):
        self.dir.mkdir(parents=True, exist_ok=True)
        for tab, name in self.FILES.items():
            path = self.dir / name
            if not path.exists():
                self._write(tab, [])

    def _read(self, tab):
        path = self.dir / self.FILES[tab]
        if not path.exists():
            return []
        with open(path, newline="", encoding="utf-8") as f:
            return [_with_columns(r, self.COLUMNS[tab]) for r in csv.DictReader(f)]

    def _write(self, tab, records):
        with open(self.dir / self.FILES[tab], "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.COLUMNS[tab])
            writer.writeheader()
            writer.writerows(_with_columns(r, self.COLUMNS[tab]) for r in records)

    def read_prospects(self):
        return [dict(r, _row=i + 2) for i, r in enumerate(self._read(sheet.PROSPECTS))]

    def update_prospects(self, updates):
        """updates: {row number: {column: value}}, agent columns only."""
        records = self._read(sheet.PROSPECTS)
        for row, changes in updates.items():
            records[row - 2].update(changes)
        self._write(sheet.PROSPECTS, records)

    def read_tasks(self):
        return self._read(sheet.TASKS)

    def append_tasks(self, tasks):
        self._write(sheet.TASKS, self._read(sheet.TASKS) + list(tasks))

    def read_do_not_contact(self):
        return self._read(sheet.DO_NOT_CONTACT)

    def append_do_not_contact(self, entry):
        self._write(sheet.DO_NOT_CONTACT, self._read(sheet.DO_NOT_CONTACT) + [entry])

    def read_agent_log(self):
        return self._read(sheet.AGENT_LOG)

    def append_agent_log(self, entry):
        self._write(sheet.AGENT_LOG, self._read(sheet.AGENT_LOG) + [entry])


class SheetsStore:
    """Google Sheets via a service account.

    Set GOOGLE_SERVICE_ACCOUNT_FILE to the service account's JSON key file and share
    the spreadsheet with the service account's email as an editor.
    """

    def __init__(self, spreadsheet_id):
        import gspread

        key_file = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE")
        if not key_file:
            raise RuntimeError("set GOOGLE_SERVICE_ACCOUNT_FILE to the service account JSON key file")
        self.gspread = gspread
        self.book = gspread.service_account(filename=key_file).open_by_key(spreadsheet_id)

    def _ws(self, tab):
        return self.book.worksheet(tab)

    def _records(self, tab, columns):
        values = self._ws(tab).get_all_values()
        if not values:
            return []
        header = values[0]
        return [_with_columns(dict(zip(header, row)), columns) for row in values[1:]]

    def setup(self, cfg):
        """Create missing tabs with headers, dropdowns, and a warning on agent-owned columns."""
        from . import sheet_setup

        sheet_setup.setup_spreadsheet(self.book, cfg)

    def read_prospects(self):
        return [dict(r, _row=i + 2) for i, r in enumerate(self._records(sheet.PROSPECTS, sheet.PROSPECT_COLUMNS))]

    def update_prospects(self, updates):
        if not updates:
            return
        ws = self._ws(sheet.PROSPECTS)
        header = ws.row_values(1)
        data = []
        for row, changes in updates.items():
            for column, value in changes.items():
                col = header.index(column) + 1
                data.append({"range": self.gspread.utils.rowcol_to_a1(row, col), "values": [[value]]})
        ws.batch_update(data, value_input_option="RAW")

    def read_tasks(self):
        return self._records(sheet.TASKS, sheet.TASK_COLUMNS)

    def append_tasks(self, tasks):
        rows = [[str(t.get(c, "")) for c in sheet.TASK_COLUMNS] for t in tasks]
        if rows:
            self._ws(sheet.TASKS).append_rows(rows, value_input_option="RAW")

    def read_do_not_contact(self):
        return self._records(sheet.DO_NOT_CONTACT, sheet.DNC_COLUMNS)

    def append_do_not_contact(self, entry):
        self._ws(sheet.DO_NOT_CONTACT).append_rows([[str(entry.get(c, "")) for c in sheet.DNC_COLUMNS]], value_input_option="RAW")

    def read_agent_log(self):
        return self._records(sheet.AGENT_LOG, sheet.AGENT_LOG_COLUMNS)

    def append_agent_log(self, entry):
        self._ws(sheet.AGENT_LOG).append_rows([[str(entry.get(c, "")) for c in sheet.AGENT_LOG_COLUMNS]], value_input_option="RAW")
