from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from rapidfuzz import fuzz
import time
import re

from app.database import get_db
from app.models import Beer, Price, PriceHistory, PriceAlert

router = APIRouter()

_cache = {"data": None, "timestamp": 0}
_stats_cache = {"data": None, "timestamp": 0}
CACHE_TTL = 3600


def clear_cache():
    _cache["data"] = None
    _cache["timestamp"] = 0
    _stats_cache["data"] = None
    _stats_cache["timestamp"] = 0


# ──────────────────────────────────────────────────────────────────────
# ROBUST GROUPING ALGORITHM
# ──────────────────────────────────────────────────────────────────────
# Strategi:
#   1. Normalisering: ASCII, lowercase, fjern volumen/ABV/separatorer
#   2. Synonymer: trippel→tripel, west coast ipa→ipa osv.
#   3. Style fingerprint: udtrækker øl-stil (DUBBEL, TRIPEL, IPA…)
#      → To øl med FORSKELLIG eksklusiv stil må ALDRIG merges
#   4. Hård gate: volume_cl skal matche (tolerance for None)
#   5. Hård gate: ABV skal være indenfor 0.4 procentpoint (hvis kendt)
#   6. Fuzzy score på det rensede navn (token_set_ratio)
#   7. Bonus for matchende ABV, bryggeri, style fingerprint
#   8. Threshold 82 — under det matches der ikke
# ──────────────────────────────────────────────────────────────────────

# Eksklusive stilarter — to forskellige af disse må ALDRIG merges
# Rækkefølgen betyder noget for entydig fingerprinting
EXCLUSIVE_STYLES = [
    # Belgiske — kritisk at Dubbel/Tripel/Quad ikke forveksles
    ("QUADRUPEL",      ["quadrupel", "quadruple", " quad "]),
    ("TRIPEL",         ["tripel", "trippel", "tripple"]),
    ("DUBBEL",         ["dubbel"]),
    # IPA — alle varianter samles under én paraply
    ("IPA",            ["ipa", "india pale ale"]),
    # Mørke stilarter
    ("IMPERIAL_STOUT", ["imperial stout", "russian imperial"]),
    ("STOUT",          ["stout"]),
    ("PORTER",         ["porter"]),
    ("BARLEYWINE",     ["barleywine", "barley wine"]),
    # Lyse stilarter
    ("PILSNER",        ["pilsner", "pilsener", " pils "]),
    ("LAGER",          ["lager", "helles"]),
    ("WEIZEN",         ["weizen", "weisse", "witbier", "hvedeoel"]),
    ("SAISON",         ["saison", "farmhouse"]),
    ("SOUR",           ["sour", "gose", "lambic", "gueuze", "berliner"]),
    ("BOCK",           ["bock"]),
    ("PALE_ALE",       ["pale ale", " apa "]),
    ("BROWN_ALE",      ["brown ale"]),
    ("BLONDE",         ["blonde ale", "blond ale"]),
    ("AMBER",          ["amber"]),
    ("RADLER",         ["radler", "shandy"]),
    ("ALKOHOLFRI",     ["alkoholfri", "alcohol free", "non-alcoholic", "0,0%", "0.0%"]),
]

# Synonymer der konverteres FØR fuzzy matching
SYNONYMS = [
    # Stavevarianter
    (r"\btrippel\b", "tripel"),
    (r"\btripple\b", "tripel"),
    (r"\bquadruple\b", "quadrupel"),
    # IPA-varianter — alle reduceres til "ipa"
    (r"\bwest coast ipa\b", "ipa"),
    (r"\bwcipa\b", "ipa"),
    (r"\bnew england ipa\b", "ipa"),
    (r"\bneipa\b", "ipa"),
    (r"\bhazy ipa\b", "ipa"),
    (r"\bsession ipa\b", "ipa"),
    (r"\bdouble ipa\b", "ipa"),
    (r"\bdipa\b", "ipa"),
    (r"\bimperial ipa\b", "ipa"),
    (r"\bblack ipa\b", "ipa"),
    (r"\bindia pale ale\b", "ipa"),
    # "trappist" er beskrivelse, ikke ID
    (r"\btrappist\b", ""),
    # Nationaliteter
    (r"\b(belgisk|dansk|tysk|engelsk|hollandsk|belgian|german|dutch|american)\b", ""),
    # Generiske ord
    (r"\b(premium|classic|original|strong|special)\b", ""),
    (r"\b(oekologisk|organic|eco|bio)\b", ""),
]


def _strip_accents(s: str) -> str:
    """Konverterer danske/europæiske tegn til ASCII."""
    return (s.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
             .replace("Æ", "ae").replace("Ø", "oe").replace("Å", "aa")
             .replace("é", "e").replace("è", "e").replace("ê", "e")
             .replace("á", "a").replace("à", "a").replace("â", "a")
             .replace("ü", "u").replace("ö", "o").replace("ä", "a"))


def normalize_name(name: str, abv=None, volume=None):
    """
    Aggressiv normalisering — fjerner ALT der ikke er identifikator-info.
    Returnerer en streng der bruges til fuzzy sammenligning.
    """
    if not name:
        return ""

    s = _strip_accents(name.lower())

    # Fjern volumen: 33cl, 0,33 l, 500 ml
    s = re.sub(r"\d+[.,]?\d*\s?(cl|ml|l|liter)\b\.?", " ", s)

    # Fjern ABV: 9,5%, 9.5 %, 9%
    s = re.sub(r"\d+[.,]\d+\s?%", " ", s)
    s = re.sub(r"\d+\s?%", " ", s)

    # Erstat separatorer med mellemrum
    s = re.sub(r"[-–—_/|*,.()\[\]]", " ", s)

    # Anvend synonymer
    for pattern, replacement in SYNONYMS:
        s = re.sub(pattern, replacement, s)

    # Behold kun bogstaver, cifre, mellemrum
    s = re.sub(r"[^a-z0-9\s]", " ", s)

    # Sammenfold mellemrum
    s = re.sub(r"\s+", " ", s).strip()

    return s


def style_fingerprint(name: str) -> set:
    """
    Returnerer sæt af eksklusive stilarter fundet i navnet.
    Hård gate: to øl med konflikterende stilarter må aldrig merges.
    """
    s = " " + _strip_accents(name.lower()) + " "
    s = re.sub(r"[-–—_/|*,.()\[\]]", " ", s)

    found = set()
    for style, keywords in EXCLUSIVE_STYLES:
        for kw in keywords:
            if kw in s:
                found.add(style)
                break
    return found


def styles_compatible(fp_a: set, fp_b: set) -> bool:
    """
    To øl er stil-kompatible HVIS:
    - Mindst én har intet fingerprint (ingen stil-info), ELLER
    - De har præcis samme fingerprint, ELLER
    - Den ene er delmængde af den anden
    """
    if not fp_a or not fp_b:
        return True
    if fp_a == fp_b:
        return True
    if fp_a.issubset(fp_b) or fp_b.issubset(fp_a):
        return True
    return False


def volumes_compatible(v_a, v_b) -> bool:
    """Volume er hård gate (None accepteres)."""
    if v_a is None or v_b is None:
        return True
    return abs(v_a - v_b) < 0.5


def abv_compatible(a_a, a_b) -> bool:
    """ABV er hård gate — max 0.4 procentpoint forskel."""
    if a_a is None or a_b is None:
        return True
    return abs(a_a - a_b) <= 0.4


def similarity_score(name_a, name_b, abv_a, abv_b, brewery_a, brewery_b, fp_a, fp_b):
    """
    Samlet match-score 0-100+.
    token_set_ratio er bedst når ord står i forskellig rækkefølge.
    """
    if not name_a or not name_b:
        return 0.0

    base = fuzz.token_set_ratio(name_a, name_b)

    if abv_a is not None and abv_b is not None:
        diff = abs(abv_a - abv_b)
        if diff <= 0.1:
            base += 8
        elif diff <= 0.3:
            base += 4

    if brewery_a and brewery_b:
        bn_a = _strip_accents(brewery_a.lower()).strip()
        bn_b = _strip_accents(brewery_b.lower()).strip()
        if bn_a == bn_b and bn_a:
            base += 6

    if fp_a and fp_b and fp_a == fp_b:
        base += 4

    return base


MATCH_THRESHOLD = 82.0


def build_beer_list(db: Session):
    """
    Bygger den grupperede ølliste med fuzzy matching på tværs af shops.
    """
    now = time.time()

    if _cache["data"] is not None and (now - _cache["timestamp"]) < CACHE_TTL:
        return _cache["data"]

    beers = db.query(Beer).options(joinedload(Beer.prices)).all()

    # Sortér så øl med flest prices behandles først — giver stabile gruppe-ankre
    beers = sorted(beers, key=lambda b: len(b.prices or []), reverse=True)

    grouped = {}
    counter = 0

    for beer in beers:
        if not beer.prices:
            continue

        norm = normalize_name(beer.name)
        fp = style_fingerprint(beer.name)
        vol = beer.volume_cl
        abv = beer.abv
        brewery = beer.brewery

        # Find bedste eksisterende gruppe
        best_key = None
        best_score = 0.0

        for key, g in grouped.items():
            # Hård gate 1: stilarter må ikke konflikte (Dubbel ≠ Tripel)
            if not styles_compatible(fp, g["_fingerprint"]):
                continue
            # Hård gate 2: volume skal matche
            if not volumes_compatible(vol, g.get("volume_cl")):
                continue
            # Hård gate 3: ABV skal være tæt på
            if not abv_compatible(abv, g.get("abv")):
                continue

            score = similarity_score(
                norm, g["_normalized"],
                abv, g.get("abv"),
                brewery, g.get("brewery"),
                fp, g["_fingerprint"],
            )

            if score > best_score:
                best_score = score
                best_key = key

        if best_key and best_score >= MATCH_THRESHOLD:
            target = grouped[best_key]
            for p in beer.prices:
                target["prices"].append({
                    "shop": p.shop_name,
                    "shop_name": p.shop_name,
                    "price": p.price_dkk,
                    "price_dkk": p.price_dkk,
                    "url": p.url,
                    "discount_pct": p.discount_pct or 0,
                    "old_price": p.old_price if hasattr(p, "old_price") else None,
                })
            # Udfyld manglende metadata
            if not target.get("image") and beer.image:
                target["image"] = beer.image
            if not target.get("brewery") and brewery:
                target["brewery"] = brewery
            if not target.get("type") and beer.type:
                target["type"] = beer.type
            if target.get("abv") is None and abv is not None:
                target["abv"] = abv
            if target.get("volume_cl") is None and vol is not None:
                target["volume_cl"] = vol
            target["_fingerprint"] = target["_fingerprint"] | fp
        else:
            # Ny gruppe
            counter += 1
            key = f"g_{counter}"
            grouped[key] = {
                "id": beer.id,
                "name": beer.name,
                "image": beer.image,
                "type": beer.type,
                "abv": abv,
                "volume_cl": vol,
                "brewery": brewery,
                "category": beer.category if hasattr(beer, "category") else None,
                "_normalized": norm,
                "_fingerprint": fp,
                "prices": [
                    {
                        "shop": p.shop_name,
                        "shop_name": p.shop_name,
                        "price": p.price_dkk,
                        "price_dkk": p.price_dkk,
                        "url": p.url,
                        "discount_pct": p.discount_pct or 0,
                        "old_price": p.old_price if hasattr(p, "old_price") else None,
                    }
                    for p in beer.prices
                ],
            }

    # Slutbehandling: dedupliker shops, beregn min/max
    result = []
    for g in grouped.values():
        unique_shops = {}
        for p in g["prices"]:
            shop = p["shop_name"]
            if shop not in unique_shops or p["price"] < unique_shops[shop]["price"]:
                unique_shops[shop] = p

        prices = sorted(unique_shops.values(), key=lambda x: x["price"])
        if not prices:
            continue

        cheapest = prices[0]
        max_discount = max((p["discount_pct"] or 0) for p in prices)

        # Fjern interne felter før frontend
        g.pop("_normalized", None)
        g.pop("_fingerprint", None)

        g["prices"] = prices
        g["cheapest_price"] = cheapest["price"]
        g["min_price"] = cheapest["price"]
        g["shop"] = cheapest["shop_name"]
        g["discount_pct"] = cheapest["discount_pct"]
        g["max_discount_pct"] = max_discount

        result.append(g)

    result.sort(key=lambda b: b["cheapest_price"])

    _cache["data"] = result
    _cache["timestamp"] = now

    return result


# ──────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ──────────────────────────────────────────────────────────────────────

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):

    now = time.time()

    if (
        _stats_cache["data"] is not None
        and (now - _stats_cache["timestamp"]) < CACHE_TTL
    ):
        return JSONResponse(content=_stats_cache["data"])

    active_beer_ids = db.query(
        Price.beer_id
    ).distinct().subquery()

    total = db.query(Beer).filter(
        Beer.id.in_(active_beer_ids)
    ).count()

    deals = db.query(
        Price.beer_id
    ).filter(
        Price.discount_pct > 0
    ).distinct().count()

    shops = db.query(
        Price.shop_name
    ).distinct().all()

    shop_names = sorted([
        s[0]
        for s in shops
        if s[0]
    ])

    cheapest = db.query(
        func.min(Price.price_dkk)
    ).scalar() or 0

    all_beers = build_beer_list(db)

    types = sorted(list(set(
        b["type"]
        for b in all_beers
        if b.get("type")
    )))

    result = {
        "total": total,
        "deals": deals,
        "shops": len(shop_names),
        "shop_names": shop_names,
        "types": types,
        "cheapest": round(cheapest, 0)
    }

    _stats_cache["data"] = result
    _stats_cache["timestamp"] = now

    return JSONResponse(content=result)


@router.get("/beers")
def get_beers_paginated(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    q: str = Query(None),
    shop: str = Query(None),
    sort: str = Query("price-asc"),
    deals_only: bool = Query(False),
    alcohol_free: bool = Query(False),
    smagekasse: bool = Query(False),
    beer_types: str = Query(None),
    min_price: float = Query(None),
    max_price: float = Query(None),
    abv_min: float = Query(None),
    abv_max: float = Query(None),
):

    all_beers = build_beer_list(db)

    filtered = all_beers

    if q:

        q_lower = q.lower()

        filtered = [
            b for b in filtered
            if (
                q_lower in b["name"].lower()
                or q_lower in (b.get("brewery") or "").lower()
            )
        ]

    if shop and shop != "all":

        filtered = [
            b for b in filtered
            if any(
                p["shop_name"] == shop
                for p in b["prices"]
            )
        ]

    if deals_only:

        filtered = [
            b for b in filtered
            if b["max_discount_pct"] > 0
        ]

    if alcohol_free:

        filtered = [
            b for b in filtered
            if (
                b.get("abv") is not None
                and b["abv"] <= 0.5
            )
        ]

    if smagekasse:

        filtered = [
            b for b in filtered
            if b.get("category") == "smagekasse"
        ]

    else:

        if not q:

            filtered = [
                b for b in filtered
                if b.get("category") != "smagekasse"
            ]

    if beer_types and beer_types != "all":

        types_list = [
            t.strip()
            for t in beer_types.split(",")
            if t.strip()
        ]

        if types_list:

            filtered = [
                b for b in filtered
                if b.get("type") in types_list
            ]

    if min_price is not None:

        filtered = [
            b for b in filtered
            if b["min_price"] >= min_price
        ]

    if max_price is not None:

        filtered = [
            b for b in filtered
            if b["min_price"] <= max_price
        ]

    if abv_min is not None:

        filtered = [
            b for b in filtered
            if (
                b.get("abv") is not None
                and b["abv"] >= abv_min
            )
        ]

    if abv_max is not None:

        filtered = [
            b for b in filtered
            if (
                b.get("abv") is not None
                and b["abv"] <= abv_max
            )
        ]

    if sort == "price-asc":

        filtered.sort(
            key=lambda b: b["min_price"]
        )

    elif sort == "price-desc":

        filtered.sort(
            key=lambda b: b["min_price"],
            reverse=True
        )

    elif sort == "discount":

        filtered.sort(
            key=lambda b: b["max_discount_pct"],
            reverse=True
        )

    elif sort == "name":

        filtered.sort(
            key=lambda b: b["name"]
        )

    elif sort == "shops":

        filtered.sort(
            key=lambda b: len(b["prices"]),
            reverse=True
        )

    total = len(filtered)

    start = (page - 1) * limit
    end = start + limit

    page_data = filtered[start:end]

    return JSONResponse(content={
        "beers": page_data,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
        "has_more": end < total
    })


@router.get("/beers-with-prices")
def get_beers_legacy(db: Session = Depends(get_db)):

    return JSONResponse(
        content=build_beer_list(db)
    )


@router.get("/ui", response_class=HTMLResponse)
def ui():

    return """
    <html>
        <head>
            <title>BeerSniffer</title>
        </head>
        <body>
            <h1>🍺 BeerSniffer API</h1>
            <p>
                Brug <a href="/docs">/docs</a>
                for API dokumentation.
            </p>
        </body>
    </html>
    """