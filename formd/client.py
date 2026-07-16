"""Polite HTTP client for SEC EDGAR.

SEC's access rules are simple and public: identify yourself in the User-Agent
and stay under 10 requests per second. This client declares a contact and
throttles well below that ceiling, then retries on the transient failures that
a busy public archive throws.
"""

import os
import time
import logging
import requests

log = logging.getLogger(__name__)

# SEC asks callers to identify themselves with a name and a working contact.
# That is their rule, not a workaround, so set EDGAR_USER_AGENT before running:
#   export EDGAR_USER_AGENT="Your Name you@example.com"
USER_AGENT = os.environ.get("EDGAR_USER_AGENT", "").strip()

# SEC permits 10 requests/second. We stay far under it: there is no upside to
# crowding a free public archive.
MIN_INTERVAL = 0.25

RETRY_STATUS = {403, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4


def _is_missing(resp):
    """True when the archive means "no such file".

    EDGAR's archive sits on S3 without list permission, so a missing key comes
    back as 403 AccessDenied rather than 404. A real rate limit is also a 403,
    but says "Request Rate Threshold Exceeded", so the body is what separates
    "this date has no index" from "you are going too fast".
    """
    if resp.status_code == 404:
        return True
    if resp.status_code == 403 and "AccessDenied" in resp.text[:500]:
        return True
    return False


class EdgarClient:
    def __init__(self, user_agent=None, min_interval=MIN_INTERVAL):
        user_agent = user_agent or USER_AGENT
        if not user_agent:
            raise RuntimeError(
                "Set EDGAR_USER_AGENT to a name and contact address, e.g. "
                '"Jane Doe jane@example.com". SEC requires callers to identify '
                "themselves, and requests without it get blocked."
            )

        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"}
        )
        self.min_interval = min_interval
        self._last_call = 0.0

    def _wait(self):
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.monotonic()

    def get(self, url, allow_missing=False):
        """GET with throttling and backoff.

        Returns the response, or None when allow_missing and the archive
        answers 404 (a normal outcome for dates with no index).
        """
        backoff = 1.0
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._wait()
            try:
                resp = self.session.get(url, timeout=45)
            except requests.RequestException as exc:
                log.warning("request failed (%s/%s) %s: %s", attempt, MAX_ATTEMPTS, url, exc)
                time.sleep(backoff)
                backoff *= 2
                continue

            if resp.status_code == 200:
                return resp
            if allow_missing and _is_missing(resp):
                return None
            if resp.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
                log.warning("status %s (%s/%s) %s", resp.status_code, attempt, MAX_ATTEMPTS, url)
                time.sleep(backoff)
                backoff *= 2
                continue

            resp.raise_for_status()

        raise RuntimeError(f"gave up after {MAX_ATTEMPTS} attempts: {url}")
