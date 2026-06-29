"""
Finder KILDEN til 'Best Before'-datoer i brewery-feltet.

Koerer alle scrapere, og for hvert item tjekker den om 'brewery' ser ud
som en holdbarhedsdato. Grupperer fund pr. butik, saa vi ved hvilken
scraper der skal fikses.

Read-only: skriver intet til Supabase eller data.json.

Koeres fra repo-roden:  python tools\find_brewery_kilde.py
"""
import sys
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.scrapers.brygshoppen import scrape_brygshoppen
from app.scrapers.agoodcase import scrape_agoodcase
from app.scrapers.beershoppen import scrape_beershoppen
from app.scrapers.bestofbeers import scrape_bestofbeers
from app.scrapers.oeltanken import scrape_oeltanken
from app.scrapers.beerme import scrape_beerme
from app.scrapers.vildmedvin import scrape_vildmedvin

SCRAPERS = [
    ("Brygshoppen", scrape_brygshoppen),
    ("A Good Case", scrape_agoodcase),
    ("Beershoppen", scrape_beershoppen),
    ("Best of Beers", scrape_bestofbeers),
    ("Oeltanken", scrape_oeltanken),
    ("Beer Me", scrape_beerme),
    ("Vild med Vin", scrape_vildmedvin),
]

BAD = re.compile(
    r"best\s*before|holdbar|\d{2}[/-]\d{2}[/-]\d{2,4}|udl[\u00f8o]ber",
    re.I,
)


def main():
    print("Koerer alle scrapere og tjekker brewery-feltet...\n")
    total_bad = 0
    for name, fn in SCRAPERS:
        try:
            items = fn()
        except Exception as e:
            print(f"{name:<15} FEJL: {e}")
            continue
        bad = [it for it in items if it.get("brewery") and BAD.search(str(it.get("brewery")))]
        flag = "  <-- KILDE!" if bad else ""
        print(f"{name:<15} {len(bad):>4} af {len(items):>4} har dato i brewery{flag}")
        total_bad += len(bad)
        for it in bad[:3]:
            print(f"      [{it.get('brewery')}]  <- {str(it.get('name'))[:50]}")
    print(f"\nI alt {total_bad} items med dato i brewery paa tvaers af butikker.")
    if total_bad == 0:
        print("Ingen aktiv scraper laegger datoer i brewery lige nu - forureningen var historisk.")


if __name__ == "__main__":
    main()