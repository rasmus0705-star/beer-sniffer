from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
import time

from app.database import get_db
from app.models import Beer, Price, PriceHistory, PriceAlert
from app.services.matching import (
    normalize_for_matching,
    style_fingerprint,
    styles_compatible,
    volumes_compatible,
    abv_compatible,
    breweries_compatible,
    similarity_score,
    has_meaningful_overlap,
    required_threshold,
    MATCH_THRESHOLD,
)

router = APIRouter()

_cache = {"data": None, "timestamp": 0}
_stats_cache = {"data": None, "timestamp": 0}
CACHE_TTL = 3600


def clear_cache():
    _cache["data"] = None
    _cache["timestamp"] = 0
    _stats_cache["data"] = None
    _stats_cache["timestamp"] = 0


def build_beer_list(db: Session):
    now = time.time()

    if _cache["data"] is not None and (now - _cache["timestamp"]) < CACHE_TTL:
        return _cache["data"]

    beers = db.query(Beer).options(joinedload(Beer.prices)).all()
    beers = sorted(beers, key=lambda b: len(b.prices or []), reverse=True)

    grouped = {}
    counter = 0

    for beer in beers:
        if not beer.prices:
            continue

        norm = normalize_for_matching(beer.name)
        fp = style_fingerprint(beer.name)
        vol = beer.volume_cl
        abv = beer.abv
        brewery = beer.brewery

        best_key = None
        best_score = 0.0
        best_threshold = MATCH_THRESHOLD

        for key, g in grouped.items():
            if not styles_compatible(fp, g["_fingerprint"]):
                continue
            if not volumes_compatible(vol, g.get("volume_cl")):
                continue
            if not abv_compatible(abv, g.get("abv")):
                continue
            if not breweries_compatible(brewery, g.get("brewery"), beer.name, g.get("name")):
                continue
            if not has_meaningful_overlap(beer.name, g.get("name")):
                continue

            score = similarity_score(
                norm, g["_normalized"],
                abv, g.get("abv"),
                brewery, g.get("brewery"),
                fp, g["_fingerprint"],
            )

            threshold = required_threshold(
                abv, g.get("abv"),
                vol, g.get("volume_cl"),
                brewery, g.get("brewery"),
            )

            if score > best_score:
                best_score = score
                best_key = key
                best_threshold = threshold

        if best_key and best_score >= best_threshold:
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
            if any(p["shop_name"] == shop for p in b["prices"])
        ]

    if deals_only:
        filtered = [b for b in filtered if b["max_discount_pct"] > 0]

    if alcohol_free:
        filtered = [
            b for b in filtered
            if b.get("abv") is not None and b["abv"] <= 0.5
        ]

    if smagekasse:
        filtered = [b for b in filtered if b.get("category") == "smagekasse"]
    else:
        if not q:
            filtered = [b for b in filtered if b.get("category") != "smagekasse"]

    if beer_types and beer_types != "all":
        types_list = [t.strip() for t in beer_types.split(",") if t.strip()]
        if types_list:
            filtered = [b for b in filtered if b.get("type") in types_list]

    if min_price is not None:
        filtered = [b for b in filtered if b["min_price"] >= min_price]

    if max_price is not None:
        filtered = [b for b in filtered if b["min_price"] <= max_price]

    if abv_min is not None:
        filtered = [
            b for b in filtered
            if b.get("abv") is not None and b["abv"] >= abv_min
        ]

    if abv_max is not None:
        filtered = [
            b for b in filtered
            if b.get("abv") is not None and b["abv"] <= abv_max
        ]

    if sort == "price-asc":
        filtered.sort(key=lambda b: b["min_price"])
    elif sort == "price-desc":
        filtered.sort(key=lambda b: b["min_price"], reverse=True)
    elif sort == "discount":
        filtered.sort(key=lambda b: b["max_discount_pct"], reverse=True)
    elif sort == "name":
        filtered.sort(key=lambda b: b["name"])
    elif sort == "shops":
        filtered.sort(key=lambda b: len(b["prices"]), reverse=True)

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
    return JSONResponse(content=build_beer_list(db))


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