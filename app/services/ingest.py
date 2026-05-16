from sqlalchemy.orm import Session

from app.models import Beer, Price, PriceHistory, PriceAlert
from app.utils.normalize import normalize_name
from app.services.matching import (
    normalize_for_matching,
    style_fingerprint,
    styles_compatible,
    volumes_compatible,
    abv_compatible,
    breweries_compatible,
    similarity_score,
    MATCH_THRESHOLD,
)


def find_best_match(item_norm, item_fp, item_vol, item_abv, item_brewery, item_name_for_brewery, candidate_beers):
    """
    Bruger samme robust logik som beers.py — style fingerprint, ABV/volume/brewery gates,
    fuzzy similarity med bonuses.
    """
    best_score = 0.0
    best_beer = None

    for beer in candidate_beers:
        beer_fp = style_fingerprint(beer.name)

        # Hård gate 1: stilarter (Dubbel ≠ Tripel)
        if not styles_compatible(item_fp, beer_fp):
            continue

        # Hård gate 2: volume
        if not volumes_compatible(item_vol, beer.volume_cl):
            continue

        # Hård gate 3: ABV
        if not abv_compatible(item_abv, beer.abv):
            continue

        # Hård gate 4: bryggeri (NY) — sender også navne for fallback-matching
        if not breweries_compatible(item_brewery, beer.brewery, item_name_for_brewery, beer.name):
            continue

        beer_norm = normalize_for_matching(beer.name)
        score = similarity_score(
            item_norm, beer_norm,
            item_abv, beer.abv,
            item_brewery, beer.brewery,
            item_fp, beer_fp,
        )

        if score > best_score:
            best_score = score
            best_beer = beer

    if best_score >= MATCH_THRESHOLD:
        return best_beer

    return None


def ingest_batch(db: Session, items: list[dict]):
    if not items:
        return

    all_beers = db.query(Beer).all()

    beers_by_volume = {}
    beers_with_no_volume = []
    for beer in all_beers:
        vol = beer.volume_cl
        if vol is None:
            beers_with_no_volume.append(beer)
        else:
            beers_by_volume.setdefault(vol, []).append(beer)

    shop_names = list(set(item["shop_name"] for item in items))

    new_prices = []
    new_histories = []

    for i, item in enumerate(items):
        item_name = item["name"]
        item_norm = normalize_for_matching(item_name)
        item_fp = style_fingerprint(item_name)
        item_vol = item.get("volume_cl")
        item_abv = item.get("abv")
        item_brewery = item.get("brewery")

        if item_vol is not None:
            candidates = beers_by_volume.get(item_vol, []) + beers_with_no_volume
        else:
            candidates = all_beers

        beer = find_best_match(
            item_norm, item_fp, item_vol, item_abv, item_brewery, item_name,
            candidates
        )

        if not beer:
            beer = Beer(
                name=item_name,
                normalized_name=normalize_name(item_name),
                brewery=item_brewery,
                type=item.get("type"),
                volume_cl=item_vol,
                abv=item_abv,
                image=item.get("image"),
            )
            db.add(beer)
            db.flush()

            if item_vol is None:
                beers_with_no_volume.append(beer)
            else:
                beers_by_volume.setdefault(item_vol, []).append(beer)
            all_beers.append(beer)

        if not beer.image and item.get("image"):
            beer.image = item["image"]
        if not beer.brewery and item_brewery:
            beer.brewery = item_brewery
        if not beer.type and item.get("type"):
            beer.type = item["type"]
        if beer.abv is None and item_abv is not None:
            beer.abv = item_abv
        if beer.volume_cl is None and item_vol is not None:
            beer.volume_cl = item_vol

        new_prices.append(Price(
            beer_id=beer.id,
            shop_name=item["shop_name"],
            price_dkk=item["price"],
            old_price=item.get("old_price"),
            discount_pct=item.get("discount_pct"),
            url=item.get("url"),
            available=True,
        ))

        last = (
            db.query(PriceHistory)
            .filter(
                PriceHistory.beer_id == beer.id,
                PriceHistory.shop_name == item["shop_name"]
            )
            .order_by(PriceHistory.created_at.desc())
            .first()
        )

        if not last or last.price_dkk != item["price"]:
            new_histories.append(PriceHistory(
                beer_id=beer.id,
                price_dkk=item["price"],
                shop_name=item["shop_name"],
            ))

        if (i + 1) % 100 == 0:
            print(f"✅ Behandlet {i + 1} / {len(items)} øl")

    print(f"💾 Gemmer {len(new_prices)} priser...")
    db.query(Price).filter(
        Price.shop_name.in_(shop_names)
    ).delete(synchronize_session=False)
    db.add_all(new_prices)
    db.add_all(new_histories)

    alerts = db.query(PriceAlert).filter(PriceAlert.active == True).all()
    for alert in alerts:
        for price in new_prices:
            if price.beer_id == alert.beer_id and price.price_dkk <= alert.target_price:
                print(f"🔥 ALERT: beer_id {alert.beer_id} now {price.price_dkk} kr")
                alert.active = False

    db.commit()

    try:
        from app.routers.beers import clear_cache
        clear_cache()
        print("🧹 Cache ryddet")
    except Exception as e:
        print(f"⚠️ Kunne ikke rydde cache: {e}")

    print(f"✅ Ingest færdig — {len(items)} øl behandlet")