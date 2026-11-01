"""
app/utils/shopify.py — Robust paginering af Shopify /products.json.

Brug:
    for page, products in shopify_pages("https://butik.dk", "Butik", HEADERS):
        for product in products:
            ...
Rejser ShopifyFejl, hvis en side ikke kan hentes efter flere forsøg.
"""
import time

import requests

LIMIT = 250
SIDE_PAUSE = 1.0
VENTETIDER = (5, 15, 30, 60)   # sek. før genforsøg ved 429/5xx/netværk/ikke-JSON
TOM_SIDE_TJEK = (10, 30)       # sek. før en tom side tjekkes igen


class ShopifyFejl(Exception):
    pass


def _hent_side(session, url, shop):
    sidste = "ukendt fejl"
    for vent in (0,) + VENTETIDER:
        if vent:
            print(f"   ⏳ {shop}: {sidste} — venter {vent}s og prøver igen...")
            time.sleep(vent)
        try:
            r = session.get(url, timeout=30)
        except requests.RequestException as e:
            sidste = f"netværksfejl ({e.__class__.__name__})"
            continue
        if r.status_code == 429 or r.status_code >= 500:
            sidste = f"HTTP {r.status_code}"
            ra = r.headers.get("Retry-After", "")
            if ra.isdigit():
                time.sleep(min(int(ra), 120))
            continue
        if r.status_code != 200:
            raise ShopifyFejl(f"{shop}: HTTP {r.status_code} på {url}")
        try:
            return r.json().get("products", [])
        except ValueError:
            sidste = "svaret var ikke JSON"
            continue
    raise ShopifyFejl(f"{shop}: gav op efter {len(VENTETIDER) + 1} forsøg ({sidste}) på {url}")


def shopify_pages(base_url, shop, headers, limit=LIMIT):
    session = requests.Session()
    session.headers.update(headers)
    page = 1
    while True:
        url = f"{base_url.rstrip('/')}/products.json?limit={limit}&page={page}"
        products = _hent_side(session, url, shop)
        if not products:
            for vent in TOM_SIDE_TJEK:
                print(f"   ⏳ {shop}: side {page} var tom — tjekker igen om {vent}s...")
                time.sleep(vent)
                products = _hent_side(session, url, shop)
                if products:
                    break
        if not products:
            if page == 1:
                raise ShopifyFejl(f"{shop}: første side er tom — butikken svarer ikke normalt")
            return
        yield page, products
        if len(products) < limit:
            return  # sidste side
        page += 1
        time.sleep(SIDE_PAUSE)
