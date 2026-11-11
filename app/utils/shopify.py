"""Shared, conservative pagination for public Shopify product feeds."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import random
import time

import requests

LIMIT = 250
SIDE_PAUSE_MIN = 2.0
SIDE_PAUSE_MAX = 3.5
REQUEST_TIMEOUT = 20
MAX_ATTEMPTS = 2
MAX_RETRY_AFTER = 120
FALLBACK_RETRY_AFTER = 30


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
            last_error = "HTTP 429"
            if attempt < MAX_ATTEMPTS:
                wait = _retry_after_seconds(response)
                print(f"   ⏳ {shop}: HTTP 429 — venter {wait}s som Shopify beder om, prøver én gang til...")
                time.sleep(wait)
                continue
            raise ShopifyFejl(f"{shop}: gav op efter {attempt} forsøg (HTTP 429) på side {page}",
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
    session.headers.update(headers)
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
