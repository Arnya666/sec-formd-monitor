"""Read EDGAR's daily index and pull out the Form D filings.

EDGAR publishes one index per business day listing every filing it received,
grouped by form type. Reading that index costs a single request and tells us
exactly which filings to fetch, so we never crawl blindly.
"""

import logging
from collections import namedtuple
from datetime import date, timedelta

log = logging.getLogger(__name__)

INDEX_URL = ("https://www.sec.gov/Archives/edgar/daily-index/"
             "{year}/QTR{quarter}/form.{stamp}.idx")

Filing = namedtuple("Filing", "form company cik filed accession path")


def quarter_of(day):
    return (day.month - 1) // 3 + 1


def index_url(day):
    return INDEX_URL.format(
        year=day.year, quarter=quarter_of(day), stamp=day.strftime("%Y%m%d")
    )


def _parse_row(line):
    """Split one fixed-width index row.

    Rows look like:
        D    410 Medical, Inc.    1630050    20260715    edgar/data/1630050/0001630050-26-000002.txt
    The columns are space padded, so we split from the right where the last
    three fields never contain spaces.
    """
    parts = line.rstrip().rsplit(None, 3)
    if len(parts) != 4:
        return None

    head, cik, filed, path = parts
    head = head.strip()
    if not head.startswith("D"):
        return None

    # The form type is the first token; everything after it is the company name
    form, _, company = head.partition(" ")
    if form != "D":            # skip D/A amendments and other D-prefixed forms
        return None

    accession = path.rsplit("/", 1)[-1].replace(".txt", "")
    return Filing(form, company.strip(), cik.strip(), filed.strip(), accession, path.strip())


def form_d_filings(client, day):
    """Return every original Form D filed on the given day (empty if no index)."""
    resp = client.get(index_url(day), allow_missing=True)
    if resp is None:
        log.info("no daily index for %s (weekend, holiday, or not published yet)", day)
        return []

    filings = []
    for line in resp.text.splitlines():
        row = _parse_row(line)
        if row:
            filings.append(row)

    log.info("%s: %s Form D filings", day, len(filings))
    return filings


def business_days_back(days, end=None):
    """Yield the last N calendar days, newest first.

    Weekends simply return no index, which form_d_filings handles, so there is
    no holiday calendar to keep in sync here.
    """
    end = end or date.today()
    for offset in range(days):
        yield end - timedelta(days=offset)
