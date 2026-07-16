"""Turn a Form D submission into a flat lead record.

Form D is what a company files with the SEC after raising money through an
exempt offering. The filing carries the issuer, the industry, how much was
sought, how much actually sold, and the officers behind it, which is why it
reads as a sales signal rather than a filing.
"""

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict, field

log = logging.getLogger(__name__)

DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{bare}/primary_doc.xml"
FILING_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{bare}/"

# Most Form D volume is investment vehicles: SPVs, funds and REIT shells that
# exist to hold capital, not to spend it. They have no staff and nothing to buy,
# so they are noise for lead generation even though the filings look identical.
FUND_INDUSTRIES = {
    "Pooled Investment Fund",
    "REITS and Finance",
    "Other Investment Fund",
    "Hedge Fund",
    "Private Equity Fund",
    "Venture Capital Fund",
}


@dataclass
class Lead:
    filed: str = ""
    company: str = ""
    amount_sold: int = 0
    amount_offered: int = 0
    industry: str = ""
    city: str = ""
    state: str = ""
    phone: str = ""
    executives: str = ""
    investors: int = 0
    first_sale: str = ""
    cik: str = ""
    accession: str = ""
    url: str = ""

    def as_row(self):
        return asdict(self)

    @property
    def is_fund(self):
        """True for investment vehicles rather than operating companies."""
        return self.industry in FUND_INDUSTRIES


def _text(node, path, default=""):
    found = node.find(path) if node is not None else None
    return found.text.strip() if found is not None and found.text else default


def _int(node, path):
    raw = _text(node, path)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _clean_phone(raw):
    """Drop placeholder numbers.

    Filers routinely type 000-000-0000 or 999-999-9999 into the phone field.
    An empty cell is honest; a fake number gets someone dialling nothing.
    """
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) < 10 or len(set(digits)) <= 2:
        return ""
    return raw


def _executives(root):
    """Names and roles of the people behind the raise, deduped, in filing order."""
    people = []
    seen = set()
    for person in root.findall(".//relatedPersonInfo"):
        name_node = person.find("relatedPersonName")
        first = _text(name_node, "firstName")
        last = _text(name_node, "lastName")
        name = " ".join(p for p in (first, last) if p).title()
        if not name or name in seen:
            continue
        seen.add(name)

        roles = [r.text.strip() for r in person.findall(".//relationship") if r.text]
        people.append(f"{name} ({', '.join(roles)})" if roles else name)
    return "; ".join(people)


def parse_filing(xml_text, filing):
    """Build a Lead from primary_doc.xml, or None if it is not a live Form D."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.warning("unparseable XML for %s: %s", filing.accession, exc)
        return None

    # EDGAR carries test submissions in the same feed; they are not real raises
    if _text(root, "testOrLive").upper() != "LIVE":
        log.debug("skipping test filing %s", filing.accession)
        return None

    issuer = root.find("primaryIssuer")
    offering = root.find("offeringData")
    bare = filing.accession.replace("-", "")

    return Lead(
        filed=f"{filing.filed[:4]}-{filing.filed[4:6]}-{filing.filed[6:]}",
        company=_text(issuer, "entityName") or filing.company,
        amount_sold=_int(offering, ".//totalAmountSold"),
        amount_offered=_int(offering, ".//totalOfferingAmount"),
        industry=_text(offering, ".//industryGroupType"),
        city=_text(issuer, "issuerAddress/city").title(),
        state=_text(issuer, "issuerAddress/stateOrCountry"),
        phone=_clean_phone(_text(issuer, "issuerPhoneNumber")),
        executives=_executives(root),
        investors=_int(offering, ".//totalNumberAlreadyInvested"),
        first_sale=_text(offering, ".//dateOfFirstSale/value"),
        cik=filing.cik,
        accession=filing.accession,
        url=FILING_URL.format(cik=filing.cik, bare=bare),
    )


def fetch_lead(client, filing):
    """Fetch and parse one filing. Returns None when it should be skipped."""
    bare = filing.accession.replace("-", "")
    resp = client.get(
        DOC_URL.format(cik=filing.cik, bare=bare), allow_missing=True
    )
    if resp is None:
        log.warning("no primary_doc.xml for %s", filing.accession)
        return None
    return parse_filing(resp.text, filing)
