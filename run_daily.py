"""Daily job: pull yesterday's Form D filings into a Google Sheet.

Meant to run unattended on a schedule. Configuration comes from the
environment so the same file works locally and in CI:

    GOOGLE_CREDENTIALS_FILE   path to a service account JSON
    SPREADSHEET_ID            id from the sheet URL (.../spreadsheets/d/<ID>/edit)
    WORKSHEET_NAME            tab name (default Sheet1)
    MIN_AMOUNT                ignore raises under this, USD (default 500000)
    MAX_AGE_DAYS              ignore raises whose first sale predates the filing by
                              more than this many days (default 90)
    LOOKBACK_DAYS             days to scan (default 3, to cover weekends)

Exits non-zero when the run looks broken, so a scheduler can alert on it.
Finding no new filings is not an error: the SEC does not file on weekends.
"""

import os
import sys
import logging

from formd import EdgarClient, form_d_filings, business_days_back, fetch_lead
from formd.sheets import open_sheet, append_leads

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("run_daily")


def env(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        log.error("missing required environment variable %s", name)
        sys.exit(2)
    return value


def main():
    creds = env("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    spreadsheet_id = env("SPREADSHEET_ID", required=True)
    worksheet = env("WORKSHEET_NAME", "Sheet1")
    min_amount = int(env("MIN_AMOUNT", "500000"))
    max_age = int(env("MAX_AGE_DAYS", "90"))
    lookback = int(env("LOOKBACK_DAYS", "3"))

    client = EdgarClient()

    filings = []
    for day in business_days_back(lookback):
        filings.extend(form_d_filings(client, day))

    # No index at all across the whole window means the archive is unreachable
    # or its layout moved. That is broken; a quiet weekend is not.
    if not filings:
        log.error("no filings found across %s days: treating as a failure", lookback)
        sys.exit(1)

    log.info("found %s Form D filings, fetching details", len(filings))

    leads = []
    for filing in filings:
        lead = fetch_lead(client, filing)
        if lead is None or lead.is_fund or lead.amount_sold < min_amount:
            continue
        if not lead.is_fresh(max_age):
            continue
        leads.append(lead)

    log.info("%s leads passed the filters", len(leads))

    sheet = open_sheet(creds, spreadsheet_id, worksheet)
    written = append_leads(sheet, leads)

    log.info("done: %s new rows written", written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
