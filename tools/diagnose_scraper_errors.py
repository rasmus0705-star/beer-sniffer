"""
diagnose_scraper_errors.py

Rammer de tre problematiske endpoints direkte (uden at parse JSON) og
printer status-kode, response-headers og starten af selve svaret, så vi
kan se PRÆCIS hvad der kommer tilbage i stedet for JSON.

Kør fra roden af projektet:
    python diagnose_scraper_errors.py
"""

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
}

TARGETS = [
    ("Beershoppen — side 1", "https://beershoppen.dk/products.json?limit=250&page=1"),
    ("Øltanken — side 1", "https://oltanken.dk/products.json?limit=250&page=1"),
    ("A Good Case — side 9 (den der fejler)", "https://agoodcase.dk/products.json?limit=250&page=9"),
    ("A Good Case — side 1 (kontrol, ved vi virker)", "https://agoodcase.dk/products.json?limit=250&page=1"),
]

for label, url in TARGETS:
    print("=" * 20, label, "=" * 20)
    print(f"URL: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        print(f"Status-kode: {r.status_code}")
        print(f"Content-Type: {r.headers.get('Content-Type')}")
        print(f"Content-Length: {r.headers.get('Content-Length')}")
        # Nogle CDN/anti-bot-løsninger sætter specifikke headers, tjek for dem
        for h in ("Server", "cf-mitigated", "cf-ray", "x-shopify-stage"):
            if h in r.headers:
                print(f"{h}: {r.headers[h]}")
        print(f"\nFørste 500 tegn af response body:")
        print(repr(r.text[:500]))
    except Exception as e:
        print(f"❌ Request-fejl: {type(e).__name__}: {e}")
    print()