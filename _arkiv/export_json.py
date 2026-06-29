import json
from datetime import datetime
from app.scrapers.brygshoppen import scrape_brygshoppen
from app.scrapers.agoodcase import scrape_agoodcase
from app.scrapers.beershoppen import scrape_beershoppen
from app.scrapers.beerme import scrape_beerme
from app.scrapers.oeltanken import scrape_oeltanken
from app.scrapers.bestofbeers import scrape_bestofbeers
from app.utils.normalize import normalize_name
from app.utils.overrides import load_fejlliste, apply_overrides, write_fejlliste
from rapidfuzz import fuzz

# Ensartet tærskel. De hårde gates fanger fejlene — ikke en lav tærskel.
THRESHOLD = 80
ABV_MAX_DIFF = 0.5   # blød gate: afvis match hvis ABV afviger mere end dette
# Når to butikker er uenige om bryggeriet (typisk fordi feltet er rod),
# kræves der HØJERE navne-lighed for at slå dem sammen — så vi kun matcher
# når det tydeligvis er samme øl.
BREWERY_DISAGREE_THRESHOLD = 88

# Variant-markører: ord der signalerer en SÆRLIG version af en ellers ens øl
# (fx fadlagret/årgang). Hvis det ene navn har et af disse og det andet ikke
# har præcis de samme, er det forskellige produkter -> match afvises.
# Bevidst konservativ: kun ord der reelt betyder "anden version", ikke
# almindelige stil-ord (sour, gose osv. som ofte er en øls grundform).
VARIANT_WORDS = {
    "barrel", "ba", "bourbon", "whisky", "whiskey", "cognac", "rum",
    "wine", "reserva", "reserve", "vintage", "anniversary", "jubilæum",
    "calvados", "tequila", "armagnac", "sherry", "port",
}

FEJLLISTE = "fejlliste.xlsx"


print("🍺 Henter ølpriser fra Brygshoppen...")
items = scrape_brygshoppen()
print("🍺 Henter ølpriser fra A Good Case...")
items += scrape_agoodcase()
print("🍺 Henter ølpriser fra Beershoppen...")
items += scrape_beershoppen()
print("🍺 Henter ølpriser fra Øltanken...")
items += scrape_oeltanken()
print("🍺 Henter ølpriser fra Beer Me...")
items += scrape_beerme()
print("🍺 Henter ølpriser fra Best of Beers...")
items += scrape_bestofbeers()

# Facitliste: udfyld manglende felter FØR matchning
existing = load_fejlliste(FEJLLISTE)
for item in items:
    apply_overrides(item, existing)


def _packs(v):
    """None -> 1 (enkelt). Ellers det angivne antal."""
    return v if v else 1


import re as _re

# Præfikser/ord der ikke siger noget om bryggeriets identitet
_BREWERY_NOISE = [
    "brouwerij", "bryggeri", "bryggeriet", "brewing", "brewery",
    "brewing co", "brewing co.", "co.", "co", "the", "brasserie",
    "birrificio", "browar", "cervecera", "cerveceria",
]


def _norm_brewery(b):
    """Reducér et bryggeri-navn til kerneord (lowercase, uden støj/komma)."""
    s = (b or "").lower()
    s = _re.sub(r'[,\.\-–—()0-9%]', ' ', s)      # fjern tegn, tal, årgange
    s = _re.sub(r'\b(cl|ml|l)\b', ' ', s)        # volumen-rester
    words = [w for w in s.split() if w and w not in _BREWERY_NOISE]
    return set(words)


def _brewery_match(a, b):
    """
    True hvis to bryggeri-navne sandsynligvis er samme bryggeri.
    Matcher når det ene navns kerneord er en delmængde af det andets
    (fx {'lindemans'} ⊆ {'lindemans','cuvée','rené','oude','kriek'}).
    """
    sa, sb = _norm_brewery(a), _norm_brewery(b)
    if not sa or not sb:
        return False
    # Eksakt match eller den ene er delmængde af den anden
    return sa == sb or sa <= sb or sb <= sa


def _variant_words(name):
    """Returnér sæt af variant-markører i et navn (barrel, bourbon, vintage...)."""
    words = set(_re.sub(r'[^a-zæøå0-9 ]', ' ', (name or '').lower()).split())
    return words & VARIANT_WORDS


def find_match(normalized, volume, abv, brewery, pack_count, grouped):
    best_score = 0
    best_key = None

    for key, beer in grouped.items():
        # HÅRD GATE 1 — volumen: skal være KENDT på begge OG ens.
        # (Mangler volumen => ingen match. Sikrere at lade den stå alene.)
        if volume is None or beer.get("volume_cl") is None or volume != beer["volume_cl"]:
            continue

        # HÅRD GATE 2 — antal i pakke skal være ens (enkelt vs sixpack vs kasse)
        if _packs(pack_count) != _packs(beer.get("pack_count")):
            continue

        # HÅRD GATE 2b — variant-markører skal stemme. Hvis det ene navn har
        # fx 'barrel aged', 'bourbon BA' eller en årgang som det andet mangler,
        # er det forskellige produkter (fx Abt 12 vs Abt 12 Barrel Aged).
        if _variant_words(normalized) != _variant_words(beer["normalized_name"]):
            continue

        # HÅRD GATE 3 — ABV må ikke afvige for meget (skiller fx Dubbel 7%
        # fra Tripel 9,5% fra samme bryggeri).
        if abv is not None and beer.get("abv") is not None:
            if abs(abv - beer["abv"]) > ABV_MAX_DIFF:
                continue

        # Navne-lighed. Vi tager det bedste af to metoder:
        #   token_sort_ratio  — god til normale navne i forskellig rækkefølge
        #   token_set_ratio   — bedre når ord gentages eller står i rod
        #                       (fx "Trappist Tripel ... Trappist Tripel")
        score = max(
            fuzz.token_sort_ratio(normalized, beer["normalized_name"]),
            fuzz.token_set_ratio(normalized, beer["normalized_name"]),
        )

        # BRYGGERI er et BLØDT signal — ikke en hård gate. Butikkerne skriver
        # bryggeri-feltet vidt forskelligt (produktnavn, dato, butiksnavn), så
        # det er upålideligt at blokere på. I stedet:
        #   - enige bryggerier (eller delmængde) => bonus
        #   - uenige bryggerier => kræv HØJERE navne-lighed for at matche
        if brewery and beer.get("brewery"):
            if _brewery_match(brewery, beer["brewery"]):
                score += 5                      # bonus når bryggeri stemmer
            else:
                # Bryggeri uenigt: kun match hvis navnet er meget tæt på.
                if score < BREWERY_DISAGREE_THRESHOLD:
                    continue

        # Lille ekstra bonus for næsten-identisk ABV (tie-breaker)
        if abv is not None and beer.get("abv") is not None and abs(abv - beer["abv"]) < 0.2:
            score += 5

        if score > best_score:
            best_score = score
            best_key = key

    if best_score >= THRESHOLD:
        return best_key
    return None


def _new_group(item, normalized, volume, abv, shop_name):
    return {
        "name": item["name"],
        "normalized_name": normalized,
        "type": item.get("type"),
        "brewery": item.get("brewery"),
        "volume_cl": volume,
        "pack_count": item.get("pack_count"),
        "abv": abv,
        "image": item.get("image"),
        "category": item.get("category", "øl"),
        "prices": [{
            "shop_name": shop_name,
            "price": item["price"],
            "old_price": item.get("old_price"),
            "discount_pct": item.get("discount_pct"),
            "url": item.get("url"),
            "available": True,
            "bulk_discounts": item.get("bulk_discounts"),
        }]
    }


grouped = {}
counter = 0

for item in items:
    normalized = normalize_name(item["name"])
    volume = item.get("volume_cl")
    abv = item.get("abv")
    brewery = item.get("brewery")
    pack_count = item.get("pack_count")
    shop_name = item.get("shop_name", "")
    match_key = find_match(normalized, volume, abv, brewery, pack_count, grouped)

    if match_key:
        existing_shops = [p["shop_name"] for p in grouped[match_key]["prices"]]
        if shop_name not in existing_shops:
            grouped[match_key]["prices"].append({
                "shop_name": shop_name,
                "price": item["price"],
                "old_price": item.get("old_price"),
                "discount_pct": item.get("discount_pct"),
                "url": item.get("url"),
                "available": True,
                "bulk_discounts": item.get("bulk_discounts"),
            })
            g = grouped[match_key]
            if not g["image"] and item.get("image"):
                g["image"] = item["image"]
            if not g["abv"] and abv:
                g["abv"] = abv
            if not g["volume_cl"] and volume:
                g["volume_cl"] = volume
            if not g.get("pack_count") and pack_count:
                g["pack_count"] = pack_count
            if not g.get("brewery") and brewery:
                g["brewery"] = brewery
            if not g["type"] and item.get("type"):
                g["type"] = item["type"]
        else:
            key = f"beer_{counter}"
            counter += 1
            grouped[key] = _new_group(item, normalized, volume, abv, shop_name)
    else:
        key = f"beer_{counter}"
        counter += 1
        grouped[key] = _new_group(item, normalized, volume, abv, shop_name)

beers = []
for key, beer in grouped.items():
    prices = beer["prices"]
    # Sikkerhedsnet: drop priser på 0 (eller derunder) og grupper uden
    # nogen gyldig pris — de hører ikke til i en prissammenligning.
    prices = [p for p in prices if p.get("price") and p["price"] > 0]
    if not prices:
        continue
    beer["prices"] = prices
    beer["min_price"] = min(p["price"] for p in prices)
    beer["max_discount_pct"] = max((p.get("discount_pct") or 0) for p in prices)
    beer["shop_count"] = len(prices)
    beers.append(beer)

beers.sort(key=lambda x: x["min_price"])

output = {
    "updated": datetime.now().strftime("%d-%m-%Y %H:%M"),
    "count": len(beers),
    "beers": beers
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"✅ Gemt {len(beers)} unikke øl til data.json")

# Opdatér fejllisten (bevarer dine rettelser, flagger kun nye huller)
stats = write_fejlliste(items, existing, FEJLLISTE)
print(f"📝 Fejlliste opdateret: {stats['rows']} rækker, {stats['mangler']} mangler udfyldning → {FEJLLISTE}")