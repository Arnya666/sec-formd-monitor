"""Append leads to a Google Sheet, skipping anything already recorded.

The sheet is the state store. Before writing, we read back the accession
numbers already there and drop those from the batch, so re-running the job,
retrying a failed run, or overlapping date ranges cannot produce duplicate
rows. There is no separate cursor file to fall out of sync with reality.
"""

import logging
import gspread
from google.oauth2.service_account import Credentials

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = [
    "filed", "company", "amount_sold", "amount_offered", "industry",
    "city", "state", "phone", "executives", "investors", "first_sale",
    "cik", "accession", "url",
]


def open_sheet(credentials_file, spreadsheet_id, worksheet="Sheet1"):
    """Open a worksheet by spreadsheet ID, creating the tab and header if needed.

    Opening by ID rather than by title is deliberate. gspread's open-by-title
    searches Drive, which would mean granting this service account visibility
    into every file in the account. By ID, the only scope needed is Sheets, and
    the account can reach exactly the one spreadsheet it was shared on.

    The ID is the long string in the sheet URL:
    docs.google.com/spreadsheets/d/<ID>/edit
    """
    creds = Credentials.from_service_account_file(credentials_file, scopes=SCOPES)
    client = gspread.authorize(creds)

    book = client.open_by_key(spreadsheet_id)
    try:
        sheet = book.worksheet(worksheet)
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(title=worksheet, rows=1000, cols=len(HEADERS))

    # A fresh sheet needs its header row before anything is appended
    if not sheet.row_values(1):
        sheet.append_row(HEADERS, value_input_option="RAW")
        log.info("wrote header row")

    return sheet


def existing_accessions(sheet):
    """Every accession number already in the sheet.

    Accession is EDGAR's unique id per filing, which makes it a natural key
    and lets the sheet double as the dedupe state.
    """
    try:
        column = HEADERS.index("accession") + 1
        values = sheet.col_values(column)[1:]     # skip the header
    except gspread.exceptions.APIError as exc:
        log.error("could not read the sheet: %s", exc)
        raise
    return {v.strip() for v in values if v.strip()}


def append_leads(sheet, leads):
    """Append only leads the sheet has not seen. Returns how many were written."""
    already = existing_accessions(sheet)
    fresh = [l for l in leads if l.accession not in already]

    skipped = len(leads) - len(fresh)
    if skipped:
        log.info("skipping %s leads already in the sheet", skipped)
    if not fresh:
        return 0

    rows = [[str(l.as_row()[h]) for h in HEADERS] for l in fresh]

    # One batched call: appending row by row would burn quota and, on a partial
    # failure, leave the sheet half written
    sheet.append_rows(rows, value_input_option="RAW")
    log.info("appended %s new leads", len(fresh))
    return len(fresh)
