"""Pull recent Form D filings and print them as leads.

Examples:
    python main.py --days 1
    python main.py --days 3 --min-amount 1000000
    python main.py --days 1 --state CA --csv leads.csv
"""

import argparse
import csv
import logging
import sys

from formd import EdgarClient, form_d_filings, business_days_back, fetch_lead


def money(value):
    if not value:
        return "-"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value / 1000:.0f}K"


def collect(client, days, min_amount, state, limit, operating_only):
    leads = []
    seen = set()
    skipped_funds = 0

    for day in business_days_back(days):
        filings = form_d_filings(client, day)
        for filing in filings:
            if limit and len(leads) >= limit:
                print(f"\n(stopped at the --limit of {limit}; more filings remain unread)")
                return leads, skipped_funds
            if filing.accession in seen:
                continue
            seen.add(filing.accession)

            lead = fetch_lead(client, filing)
            if lead is None:
                continue
            if operating_only and lead.is_fund:
                skipped_funds += 1
                continue
            if lead.amount_sold < min_amount:
                continue
            if state and lead.state.upper() != state.upper():
                continue

            leads.append(lead)
            print(f"  + {lead.company[:42]:44} {money(lead.amount_sold):>8}  "
                  f"{lead.state:2}  {lead.industry[:22]}")
    return leads, skipped_funds


def main():
    ap = argparse.ArgumentParser(description="Turn new SEC Form D filings into leads")
    ap.add_argument("--days", type=int, default=1, help="how many days back to scan")
    ap.add_argument("--min-amount", type=int, default=0, help="minimum amount actually raised, USD")
    ap.add_argument("--state", help="filter by issuer state, e.g. CA")
    ap.add_argument("--limit", type=int, help="stop after this many leads (useful for a quick look)")
    ap.add_argument("--operating-only", action="store_true",
                    help="drop SPVs, funds and REIT shells, keep real companies")
    ap.add_argument("--csv", help="write results to this CSV file")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )

    client = EdgarClient()
    print(f"Scanning the last {args.days} day(s) of Form D filings\n")

    leads, skipped_funds = collect(
        client, args.days, args.min_amount, args.state, args.limit, args.operating_only
    )
    leads.sort(key=lambda l: l.amount_sold, reverse=True)

    print(f"\n{len(leads)} leads")
    if skipped_funds:
        print(f"Skipped {skipped_funds} investment vehicles (SPVs, funds, REIT shells)")
    if leads:
        total = sum(l.amount_sold for l in leads)
        print(f"Total raised across these companies: {money(total)}")

    if args.csv and leads:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(leads[0].as_row().keys()))
            writer.writeheader()
            for lead in leads:
                writer.writerow(lead.as_row())
        print(f"Wrote {args.csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
