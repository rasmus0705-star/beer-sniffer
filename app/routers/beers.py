from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
import time

from app.database import get_db
from app.models import Beer, Price, PriceHistory, PriceAlert

router = APIRouter()

# ── Cache ──
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
    result = []

    for beer in beers:
        if not beer.prices:
            continue

        # Dedupliker — én pris per butik (behold billigste)
        shop_best = {}
        for p in beer.prices:
            shop = p.shop_name
            if shop not in shop_best or p.price_dkk < shop_best[shop].price_dkk:
                shop_best[shop] = p

        unique_prices = list(shop_best.values())
        if not unique_prices:
            continue

        sorted_prices = sorted(unique_prices, key=lambda p: p.price_dkk)
        cheapest = sorted_prices[0]
        max_discount = max((p.discount_pct or 0) for p in sorted_prices)

        result.append({
            "id": beer.id,
            "name": beer.name,
            "image": beer.image,
            "cheapest_price": cheapest.price_dkk,
            "min_price": cheapest.price_dkk,
            "shop": cheapest.shop_name,
            "discount_pct": cheapest.discount_pct or 0,
            "max_discount_pct": max_discount,
            "type": beer.type,
            "abv": beer.abv,
            "volume_cl": beer.volume_cl,
            "brewery": beer.brewery,
            "category": beer.category if hasattr(beer, "category") else None,
            "prices": [
                {
                    "shop": p.shop_name,
                    "shop_name": p.shop_name,
                    "price": p.price_dkk,
                    "price_dkk": p.price_dkk,
                    "url": p.url,
                    "discount_pct": p.discount_pct,
                    "old_price": p.old_price if hasattr(p, "old_price") else None,
                }
                for p in sorted_prices
            ]
        })

    result.sort(key=lambda b: b["cheapest_price"])
    _cache["data"] = result
    _cache["timestamp"] = now
    return result


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    now = time.time()
    if _stats_cache["data"] is not None and (now - _stats_cache["timestamp"]) < CACHE_TTL:
        return JSONResponse(content=_stats_cache["data"])

    active_beer_ids = db.query(Price.beer_id).distinct().subquery()
    total = db.query(Beer).filter(Beer.id.in_(active_beer_ids)).count()
    deals = db.query(Price.beer_id).filter(Price.discount_pct > 0).distinct().count()
    shops = db.query(Price.shop_name).distinct().all()
    shop_names = sorted([s[0] for s in shops if s[0]])
    cheapest = db.query(func.min(Price.price_dkk)).scalar() or 0

    result = {
        "total": total,
        "deals": deals,
        "shops": len(shop_names),
        "shop_names": shop_names,
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
    min_price: float = Query(None),
    max_price: float = Query(None),
    abv_min: float = Query(None),
    abv_max: float = Query(None),
):
    all_beers = build_beer_list(db)
    filtered = all_beers

    # Søgning
    if q:
        q_lower = q.lower()
        filtered = [b for b in filtered if q_lower in b["name"].lower() or q_lower in (b.get("brewery") or "").lower()]

    # Butik
    if shop and shop != "all":
        filtered = [b for b in filtered if any(p["shop_name"] == shop for p in b["prices"])]

    # Kun tilbud
    if deals_only:
        filtered = [b for b in filtered if b["max_discount_pct"] > 0]

    # Pris
    if min_price is not None:
        filtered = [b for b in filtered if b["min_price"] >= min_price]
    if max_price is not None:
        filtered = [b for b in filtered if b["min_price"] <= max_price]

    # ABV — filtrer kun øl med kendt ABV inden for intervallet
    if abv_min is not None:
        filtered = [b for b in filtered if b.get("abv") is not None and b["abv"] >= abv_min]
    if abv_max is not None:
        filtered = [b for b in filtered if b.get("abv") is not None and b["abv"] <= abv_max]

    # Sortering
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
    <html><head><title>BeerSniffer</title></head>
    <body><h1>🍺 BeerSniffer API</h1>
    <p>Brug <a href="/docs">/docs</a> for API dokumentation.</p>
    </body></html>
    """