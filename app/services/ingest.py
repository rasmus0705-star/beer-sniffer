from sqlalchemy.orm import Session
from rapidfuzz import fuzz

from app.models import Beer, Price, PriceHistory, PriceAlert
from app.utils.normalize import normalize_name


def find_best_match(normalized_name, volume, beers_by_volume):
    candidates = beers_by_volume.get(volume, [])
    best_score = 0
    best_beer = None

    for beer in candidates:
        score = fuzz.ratio(normalized_name, beer.normalized_name)
        if score > best_score:
            best_score = score
            best_beer = beer

    if best_score >= 85:
        return best_beer

    return None


def ingest_batch(db: Session, items: list[dict]):
    # Byg et volume-indekseret dictionary for hurtig opslag
    all_beers = db.query(Beer).all()
    beers_by_volume = {}
    for beer in all_beers:
        vol = beer.volume_cl
        if vol not in beers_by_volume:
            beers_by_volume[vol] = []
        beers_by_volume[vol].append(beer)

    # Slet gamle priser for de butikker vi opdaterer
    shop_names = list(set(item["shop_name"] for item in items))
    db.query(Price).filter(Price.shop_name.in_(shop_names)).delete(synchronize_session=False)
    db.commit()

    new_prices = []
    new_histories = []
    commit_interval = 100

    for i, item in enumerate(items):
        normalized = normalize_name(item["name"])
        volume = item.get("volume_cl")

        beer = find_best_match(normalized, volume, beers_by_volume)

        # Opret øl hvis ikke fundet
        if not beer:
            beer = Beer(
                name=item["name"],
                normalized_name=normalized,
                brewery=item.get("brewery"),
                type=item.get("type"),
                volume_cl=volume,
                abv=item.get("abv"),
                image=item.get("image"),
            )
            db.add(beer)
            db.flush()

            if volume not in beers_by_volume:
                beers_by_volume[volume] = []
            beers_by_volume[volume].append(beer)

        # Opdater billede hvis mangler
        if not beer.image and item.get("image"):
            beer.image = item["image"]

        # Saml priser
        new_prices.append(Price(
            beer_id=beer.id,
            shop_name=item["shop_name"],
            price_dkk=item["price"],
            old_price=item.get("old_price"),
            discount_pct=item.get("discount_pct"),
            url=item.get("url"),
            available=True,
        ))

        # Prishistorik
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

        # Commit hver 100 øl
        if (i + 1) % commit_interval == 0:
            db.add_all(new_prices)
            db.add_all(new_histories)
            db.commit()
            new_prices = []
            new_histories = []
            print(f"✅ Gemt {i + 1} / {len(items)} øl")

    # Gem resten
    if new_prices:
        db.add_all(new_prices)
    if new_histories:
        db.add_all(new_histories)
    db.commit()
    print(f"✅ Ingest færdig — {len(items)} øl behandlet")