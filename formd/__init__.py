"""Monitor SEC Form D filings and turn them into sales leads.

A Form D means a company just raised money, which makes it one of the cleanest
buying signals available: the filing names the company, the amount actually
sold, the industry, and the officers behind it.
"""

from .client import EdgarClient
from .index import form_d_filings, business_days_back
from .parser import Lead, fetch_lead, parse_filing

__all__ = [
    "EdgarClient",
    "form_d_filings",
    "business_days_back",
    "Lead",
    "fetch_lead",
    "parse_filing",
]
