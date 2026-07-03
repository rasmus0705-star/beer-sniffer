# -*- coding: utf-8 -*-
"""
vis_prisfald.py — viser de 10 stoerste prisfald fra data.json,
saa du kan soege paa et af navnene i browseren og se 📉-badgen.

Koer fra roden af projektet:
    python vis_prisfald.py
"""

import json

with open("data.json", encoding="utf-8") as f:
    data = json.load(f)

drops = sorted(
    [b for b in data["beers"] if b.get("price_change_7d", 0) < 0],
    key=lambda b: b["price_change_7d"],
)[:10]

if not drops:
    print("Ingen prisfald fundet i data.json.")
else:
    print(f"De {len(drops)} stoerste prisfald (seneste ~7 dage):\n")
    for b in drops:
        pris = b.get("cheapest_price", 0)
        print(f"  {b['price_change_7d']:+7.0f} kr   nu {pris:7.2f} kr   {b['name'][:55]}")