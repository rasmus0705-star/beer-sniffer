"""Shared, conservative pagination for public Shopify product feeds."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import random
import time
import os

import requests

LIMIT = 250
SIDE_PAUSE_MIN = 2.0
SIDE_PAUSE_MAX = 3.5
REQUEST_TIMEOUT = 20
MAX_ATTEMPTS = 2
MAX_RETRY_AFTER = 120
FALLBACK_RETRY_AFTER = 30
DIAGNOSTIC_BODY_LIMIT = 240
WEB_BOT_AUTH_KEYS = {
    "A Good Case": "AGOODCASE",
    "Beermatch": "BEERMATCH",
    "Beershoppen": "BEERSHOPPEN",
    "Brygshoppen": "BRYGSHOPPEN",
    "Drikbeer": "DRIKBEER",
    "Øltanken": "OELTANKEN",
}


class ShopifyFejl(Exception):
    """A Shopify request failed; status_code/page let the runner detect 429s."""

    def __init__(self, message, *, status_code=None, page=None):
        super().__init__(message)
        self.status_code = status_code
        self.page = page


def _retry_after_seconds(response):
    raw = response.headers.get("Retry-After", "").strip()
    if raw.isdigit():
        return min(int(raw), MAX_RETRY_AFTER)
    if raw:
        try:
            at = parsedate_to_datetime(raw)
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            return min(max(0, int((at - datetime.now(timezone.utc)).total_seconds())), MAX_RETRY_AFTER)
        except (TypeError, ValueError, OverflowError):
            pass
    return FALLBACK_RETRY_AFTER


def _response_diagnostics(response):
    """Return a short, useful summary of a storefront error response."""
    interesting = ("Retry-After", "Content-Type", "Server", "Powered-By",
                  "X-Request-Id", "CF-Ray")
    headers = [f"{name}={response.headers.get(name)}" for name in interesting
               if response.headers.get(name)]
    body = " ".join((getattr(response, "text", "") or "").split())
    if len(body) > DIAGNOSTIC_BODY_LIMIT:
        body = body[:DIAGNOSTIC_BODY_LIMIT] + "…"
    parts = []
    if headers:
        parts.append("headers: " + ", ".join(headers))
    if body:
        parts.append("body: " + body)
    return "; ".join(parts) or "intet response-body eller diagnostiske headers"


def _authorized_headers(shop, headers):
    """Add optional Shopify-issued Web Bot Auth values from local environment."""
    result = dict(headers)
    key = WEB_BOT_AUTH_KEYS.get(shop)
    if not key:
        return result
    prefix = f"BEERSNIFFER_SHOPIFY_{key}"
    signature_input = os.getenv(f"{prefix}_SIGNATURE_INPUT", "").strip()
    signature = os.getenv(f"{prefix}_SIGNATURE", "").strip()
    if not signature_input and not signature:
        return result
    if not signature_input or not signature:
        raise ShopifyFejl(
            f"{shop}: Web Bot Auth-konfiguration er ufuldstændig; sæt både "
            f"{prefix}_SIGNATURE_INPUT og {prefix}_SIGNATURE"
        )
    result["Signature-Input"] = signature_input
    result["Signature"] = signature
    result["Signature-Agent"] = os.getenv(
        f"{prefix}_SIGNATURE_AGENT", '"https://shopify.com"'
    ).strip()
    return result


def _hent_side(session, url, shop, page):
    last_error = "ukendt fejl"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            last_error = f"netværksfejl ({exc.__class__.__name__})"
            if attempt < MAX_ATTEMPTS:
                time.sleep(5)
                continue
            raise ShopifyFejl(f"{shop}: {last_error} på side {page}", page=page) from exc

        if response.status_code == 429:
            diagnostic = _response_diagnostics(response)
            last_error = f"HTTP 429 ({diagnostic})"
            if "local_rate_limited" in (getattr(response, "text", "") or "").lower():
                raise ShopifyFejl(
                    f"{shop}: Shopify bot-filter afviste kaldet (local_rate_limited; "
                    f"{diagnostic}). Brug butiksejerens Web Bot Auth-signatur eller et "
                    f"godkendt produktfeed; ventetid løser ikke denne afvisning. På side {page}",
                    status_code=429, page=page,
                )
            if attempt < MAX_ATTEMPTS:
                wait = _retry_after_seconds(response)
                print(f"   ⏳ {shop}: HTTP 429 — {diagnostic} — venter {wait}s som serveren beder om, prøver én gang til...")
                time.sleep(wait)
                continue
            raise ShopifyFejl(f"{shop}: gav op efter {attempt} forsøg (HTTP 429; {diagnostic}) på side {page}",
                              status_code=429, page=page)

        if response.status_code >= 500:
            last_error = f"HTTP {response.status_code}"
            if attempt < MAX_ATTEMPTS:
                time.sleep(5)
                continue
            raise ShopifyFejl(f"{shop}: gav op efter {attempt} forsøg ({last_error}) på side {page}",
                              status_code=response.status_code, page=page)

        if response.status_code != 200:
            raise ShopifyFejl(f"{shop}: HTTP {response.status_code} på side {page}",
                              status_code=response.status_code, page=page)
        try:
            payload = response.json()
        except ValueError as exc:
            raise ShopifyFejl(f"{shop}: svaret var ikke JSON på side {page}", page=page) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
            raise ShopifyFejl(f"{shop}: JSON-svaret mangler produktlisten på side {page}", page=page)
        return payload["products"]

    raise ShopifyFejl(f"{shop}: {last_error} på side {page}", page=page)


def shopify_pages(base_url, shop, headers, limit=LIMIT):
    """Yield pages; make at most one retry for a throttled or transient request."""
    session = requests.Session()
    session.headers.update(_authorized_headers(shop, headers))
    page = 1
    while True:
        url = f"{base_url.rstrip('/')}/products.json?limit={limit}&page={page}"
        products = _hent_side(session, url, shop, page)
        if not products:
            if page == 1:
                raise ShopifyFejl(f"{shop}: første side er tom — butikken svarer ikke normalt", page=page)
            return
        yield page, products
        if len(products) < limit:
            return
        page += 1
        time.sleep(random.uniform(SIDE_PAUSE_MIN, SIDE_PAUSE_MAX))
