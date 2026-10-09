import os

import pytest

from bde_prospecting import sheet
from bde_prospecting.config import load_config

# Tests never call Claude.
os.environ["AGENTGTM_DISABLE_LLM"] = "1"


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture
def make_row():
    counter = iter(range(2, 10_000))

    def make(**overrides):
        row = {c: "" for c in sheet.PROSPECT_COLUMNS}
        row.update(
            date_added="2026-10-12", bde_id="BDE-01", task_id="T-2026-10-12-BDE-01", startup="daxa",
            territory="northeast", persona="ciso", first_name="Jordan", last_name="Blake", title="CISO",
            company="Granite Trust", company_domain="granitetrust.example", company_size="1001-5000",
            industry="Banking", city="New York", state="NY", linkedin_url="https://www.linkedin.com/in/jordan-blake",
        )
        row.update(overrides)
        row["_row"] = next(counter)
        return row

    return make
