from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
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


def normalize_name(name: str, abv=None, volume=None):

    if not name:
        return ""

    name = name.lower()

    # danske bogstaver
    name = (
        name.replace("ø", "oe")
        .replace("æ", "ae")
        .replace("å", "aa")
    )

    # ensret stavemåder
    replacements = {
        "trippel": "tripel",
        "tripple": "tripel",
        "india pale ale": "ipa",
        "west coast ipa": "ipa",
        "new england ipa": "neipa",
        "new england india pale ale": "neipa",
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    # fjern alkohol %
    name = re.sub(r"\d+[.,]?\d*\s?%", "", name)

    # fjern størrelse
    name = re.sub(r"\d+[.,]?\d*\s?(cl|ml|l)", "", name)

    # fjern specialtegn
    name = re.sub(r"[^a-z0-9\s]", " ", name)

    # ord der ikke hjælper matching
    blacklist = {
        "beer",
        "ale",
        "brewery",
        "brouwerij",
        "bryggeri",
        "trappist",
        "belgian",
        "belgisk",
        "abbey",
        "strong",
        "premium",
        "classic",
        "original",
        "stk",
    }

    words = []

    for word in name.split():

        if word in blacklist:
            continue

        if len(word) <= 1:
            continue

        if word not in words:
            words.append(word)

    words = sorted(words)

    clean_name = " ".join(words)

    # rund ABV lidt grovere
    abv_key = round(float(abv), 0) if abv is not None else "na"

    # volume bruges kun til debug / fremtid
    if volume is not None:

        vol = float(volume)

        if vol < 10:
            vol = vol * 100

        vol_key = round(vol)

    else:
        vol_key = "na"

    # matcher kun på navn + abv
    return f"{clean_name}|{abv_key}"


def build_beer_list(db: Session):

    now = time.time()

    if (
        _cache["data"] is not None
        and (now - _cache["timestamp"]) < CACHE_TTL
    ):
        return _cache["data"]

    beers = db.query(Beer).options(
        joinedload(Beer.prices)
    ).all()

    grouped = {}

    for beer in beers:

        if not beer.prices:
            continue

        key = normalize_name(
            beer.name,
            beer.abv,
            beer.volume_cl
        )

        # DEBUG WESTMALLE
        if "westmalle" in beer.name.lower():

            print("DEBUG WESTMALLE")
            print("NAME:", beer.name)
            print("ABV:", beer.abv)
            print("VOL:", beer.volume_cl)
            print("KEY:", key)
            print("-------------------")

        if key not in grouped:

            grouped[key] = {
                "id": beer.id,
                "name": beer.name,
                "image": beer.image,
                "type": beer.type,
                "abv": beer.abv,
                "volume_cl": beer.volume_cl,
                "brewery": beer.brewery,
                "category": beer.category if hasattr(beer, "category") else None,
                "prices": []
            }

        for p in beer.prices:

            grouped[key]["prices"].append({
                "shop": p.shop_name,
                "shop_name": p.shop_name,
                "price": p.price_dkk,
                "price_dkk": p.price_dkk,
                "url": p.url,
                "discount_pct": p.discount_pct or 0,
                "old_price": p.old_price if hasattr(p, "old_price") else None,
            })

    result = []

    for beer in grouped.values():

        unique_shops = {}

        for p in beer["prices"]:

            shop = p["shop_name"]

            # behold billigste pris pr butik
            if (
                shop not in unique_shops
                or p["price"] < unique_shops[shop]["price"]
            ):
                unique_shops[shop] = p

        prices = sorted(
            unique_shops.values(),
            key=lambda x: x["price"]
        )

        if not prices:
            continue

        cheapest = prices[0]

        max_discount = max(
            (p["discount_pct"] or 0)
            for p in prices
        )

        beer["prices"] = prices
        beer["cheapest_price"] = cheapest["price"]
        beer["min_price"] = cheapest["price"]
        beer["shop"] = cheapest["shop_name"]
        beer["discount_pct"] = cheapest["discount_pct"]
        beer["max_discount_pct"] = max_discount

        result.append(beer)

    result.sort(
        key=lambda b: b["cheapest_price"]
    )

    _cache["data"] = result
    _cache["timestamp"] = now

    return result


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
        s[0] for s in shops if s[0]
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

    # søgning
    if q:

        q_lower = q.lower()

        filtered = [
            b for b in filtered
            if q_lower in b["name"].lower()
            or q_lower in (b.get("brewery") or "").lower()
        ]

    # butik
    if shop and shop != "all":

        filtered = [
            b for b in filtered
            if any(
                p["shop_name"] == shop
                for p in b["prices"]
            )
        ]

    # tilbud
    if deals_only:

        filtered = [
            b for b in filtered
            if b["max_discount_pct"] > 0
        ]

    # alkoholfri
    if alcohol_free:

        filtered = [
            b for b in filtered
            if b.get("abv") is not None
            and b["abv"] <= 0.5
        ]

    # smagekasser
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

    # øltyper
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

    # pris
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

    # ABV
    if abv_min is not None:

        filtered = [
            b for b in filtered
            if b.get("abv") is not None
            and b["abv"] >= abv_min
        ]

    if abv_max is not None:

        filtered = [
            b for b in filtered
            if b.get("abv") is not None
            and b["abv"] <= abv_max
        ]

    # sortering
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
def get_beers_legacy(
    db: Session = Depends(get_db)
):
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
            <p>Brug <a href="/docs">/docs</a> for API dokumentation.</p>
        </body>
    </html>
    """