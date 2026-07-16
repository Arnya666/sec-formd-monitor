# SEC Form D Monitor

Turns new SEC filings into sales leads. A company files a Form D right after it
raises money, which makes it one of the cleanest buying signals there is: the
filing names the company, how much it actually sold, the industry, and the
officers behind it.

The job runs daily, appends new raises to a Google Sheet, and skips anything
already recorded.

## Why the data is worth having

One ordinary weekday produced **48 operating companies** that had just raised a
combined **$1.16B**, from $500K seed rounds up to a $302M robotics round. Each
row carries the company, amount, city, state, industry, named executives, and a
link back to the filing.

## Access

SEC allows automated access as long as you identify yourself and stay under
10 requests/second. This client declares a contact in the `User-Agent` and
throttles to 4 requests/second, well inside the limit. No proxies, no
workarounds, nothing to apologise for.

Identify yourself before running it:

```bash
export EDGAR_USER_AGENT="Your Name you@example.com"
```

The client refuses to start without it, because SEC blocks anonymous callers.

## Three decisions worth explaining

**Investment vehicles are filtered out.** Roughly 70% of Form D volume is SPVs,
funds and REIT shells: legal wrappers that hold capital rather than spend it. On
the sample day that meant 113 of 161 filings were noise. `--operating-only`
keeps the companies that actually have staff and budgets.

**A filing date is not a funding date.** Form D covers continuing offerings and
gets filed late, so a filing that lands today can describe money raised in 2022.
Treating "filed today" as "raised today" quietly fills the sheet with cold
companies. `--max-age` compares the first sale against the filing date and drops
anything older. Issuers have 15 days from first sale to file, so most real
filings score 0 to 15 days; anything far past that is a late or continuing
offering, not fresh news.

**The sheet is the state store.** Before appending, the job reads back the
accession numbers already present and drops those from the batch. Re-running
the job, retrying a failed run, or overlapping date ranges cannot duplicate
rows, and there is no separate cursor file to drift out of sync. Changing what
gets collected means editing a filter, not repairing state.

## Usage

```bash
pip install -r requirements.txt

# Look at yesterday's filings
python main.py --days 1

# Real companies, raises over $1M, deal no older than 90 days, to CSV
python main.py --days 3 --operating-only --min-amount 1000000 --max-age 90 --csv leads.csv

# Just California
python main.py --days 5 --operating-only --state CA
```

## Running it daily

`run_daily.py` is the unattended entry point and reads its configuration from
the environment:

| Variable | Meaning | Default |
| --- | --- | --- |
| `EDGAR_USER_AGENT` | name and contact for SEC | required |
| `GOOGLE_CREDENTIALS_FILE` | service account JSON | `credentials.json` |
| `SPREADSHEET_ID` | id from the sheet URL | required |
| `WORKSHEET_NAME` | tab name | `Sheet1` |
| `MIN_AMOUNT` | ignore raises below this | `500000` |
| `MAX_AGE_DAYS` | ignore deals older than this at filing | `90` |
| `LOOKBACK_DAYS` | days to scan per run | `3` |

`.github/workflows/daily.yml` runs it on GitHub Actions on weekday mornings.
Put the service account JSON in the `GOOGLE_CREDENTIALS` repo secret and the
sheet id in `SPREADSHEET_ID`.

Set up on the Google side: create a service account, download a JSON key, then
share the target sheet with the account's email as an Editor. The account
starts with access to nothing, so that share is what grants it the sheet.

The lookback covers three days on purpose. EDGAR publishes nothing on weekends
and holidays, so a run that finds no new filings is normal, and the dedupe makes
re-reading the same days free. The job only exits non-zero when it cannot reach
the archive at all, which is the difference between "nobody filed" and "this is
broken".

## Notes from building it

EDGAR's archive sits on S3 without list permission, so a missing file returns
**403 AccessDenied rather than 404**. A retry loop that treats every 403 as rate
limiting will spin and then fail on dates that simply have no index. The client
tells the two apart by reading the response body.

gspread's `open()` looks a sheet up **by title, through the Drive API**, so it
fails with "insufficient authentication scopes" unless you hand the service
account access to Drive. `open_by_key()` needs only the Sheets scope, which
keeps the account scoped to the single spreadsheet it was shared on. Reaching
for the broader permission is the easy fix and the wrong one.

Filers also put placeholders like `000-000-0000` in the phone field. Those are
blanked rather than passed through: an empty cell is honest, a fake number
wastes someone's afternoon.

## Layout

```
formd/
  client.py   polite HTTP: user agent, throttle, retry, S3 quirk
  index.py    daily index -> Form D rows
  parser.py   filing XML -> lead record
  sheets.py   append to Google Sheets, dedupe against what is there
main.py       CLI for ad hoc pulls
run_daily.py  unattended entry point
```
