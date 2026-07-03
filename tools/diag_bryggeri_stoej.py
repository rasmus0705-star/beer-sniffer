# -*- coding: utf-8 -*-
"""
diag_bryggeri_stoej.py — READ-ONLY.

Finder oel i data.json hvis bryggeri-felt ligner et PRODUKTNAVN
fremfor et bryggeri (fx 'De Dolle, Stille Nacht, 2025, Ale,').
Det er den fejl, der oedelaegger "Flere oel fra ..."-sektionen paa
oel-siderne og giver haengende '– –' i titler.

Kendetegn der flagges:
  - komma i bryggeriet + aarstal (2019-2026) eller stilord (ale, stout,
    ipa, porter, lager ...) => hele navnet er havnet i bryggeri-feltet
  - bryggeri slutter paa komma/tankestreg (afklippet navnerest)
  - bryggeri er mistaenkeligt langt (> 40 tegn)
  - bryggeri indeholder volumen/ABV-rester ('33cl', '8%', '0,5 l')

Ingen skrivning. Koer fra roden:
    python diag_bryggeri_stoej.py
Rettes bagefter i fejlliste.xlsx' Bryggeri-kolonne (facit vinder).
"""

import json
import re
import sys
from html import unescape

FILE = "data.json"

YEAR_RE = re.compile(r"\b20(1[5-9]|2[0-9])\b")
STYLE_WORDS = re.compile(
    r"\b(ale|stout|porter|ipa|lager|pilsner|pils|tripel|dubbel|quad|"
    r"saison|sour|gueuze|lambic|bock|weissbier|weizen|blond|blonde)\b",
    re.IGNORECASE,
)
VOLABV_RE = re.compile(r"\d+\s*(cl|ml|l)\b|\d+[.,]?\d*\s*%", re.IGNORECASE)


def problems(brew):
    p = []
    if "," in brew and (YEAR_RE.search(brew) or STYLE_WORDS.search(brew)):
        p.append("komma+aarstal/stilord (ligner produktnavn)")
    if brew.rstrip().endswith((",", "-", "\u2013", "\u2014")):
        p.append("slutter paa komma/streg (afklippet)")
    if len(brew) > 40:
        p.append(f"meget langt ({len(brew)} tegn)")
    if VOLABV_RE.search(brew):
        p.append("indeholder volumen/ABV-rest")
    return p


def main():
    try:
        with open(FILE, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"❌ Fandt ikke {FILE} — koer fra projektets rod.")
        sys.exit(1)

    beers = data.get("beers", [])
    flagged = []
    for b in beers:
        brew = (b.get("brewery") or "").strip()
        if not brew:
            continue
        p = problems(unescape(brew))
        if p:
            flagged.append((b, p))

    print(f"Oel i data.json: {len(beers)}")
    print(f"Flaggede bryggeri-felter: {len(flagged)}\n")

    for b, p in sorted(flagged, key=lambda x: x[0].get("slug") or ""):
        print(f"  slug : {b.get('slug')}")
        print(f"  navn : {unescape(b.get('name') or '')}")
        print(f"  brew : {unescape(b.get('brewery') or '')!r}")
        print(f"  -> {'; '.join(p)}")
        # URL'en fra billigste pris = noeglen i fejlliste.xlsx
        prices = b.get("prices") or []
        if prices:
            print(f"  url  : {prices[0].get('url')}")
        print()

    if flagged:
        print("Rettes i fejlliste.xlsx: find raekken paa URL-noeglen og skriv")
        print("det KORREKTE bryggeri i 'Bryggeri'-kolonnen (gylden overskrift).")
        print("Facit vinder ved naeste build, og 'Flere oel fra ...' heler.")


if __name__ == "__main__":
    main()