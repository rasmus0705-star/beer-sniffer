from sqlalchemy.orm import Session
from rapidfuzz import fuzz

from app.models import Beer, Price, PriceHistory, PriceAlert
from app.utils.normalize import normalize_name


def find_best_match(normalized_name, volume, beers):
    best_score = 0
    best_beer = None

    for beer in beers:
        if beer.volume_cl != volume:
            continue

        score = fuzz.ratio(normalized_name, beer.normalized_name)

        if score > best_score:
            best_score = score
            best_beer = beer

    # 🔥 threshold
    if best_score >= 85:
        return best_beer

    return None


def ingest_batch(db: Session, items: list[dict]):
    beers = db.query(Beer).all()

    for item in items:
        normalized = normalize_name(item["name"])
        volume = item.get("volume_cl")

        beer = find_best_match(normalized, volume, beers)

        # 🔥 create hvis ikke fundet
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
            db.commit()
            db.refresh(beer)

            beers.append(beer)

        # 🔥 update image hvis mangler
        if not beer.image and item.get("image"):
            beer.image = item["image"]

        # 🔥 price
        price = Price(
            beer_id=beer.id,
            shop_name=item["shop_name"],
            price_dkk=item["price"],
            old_price=item.get("old_price"),
            discount_pct=item.get("discount_pct"),
            url=item.get("url"),
            available=True,
        )
        db.add(price)

        # 🔥 history
        last = (
            db.query(PriceHistory)
            .filter(PriceHistory.beer_id == beer.id)
            .order_by(PriceHistory.created_at.desc())
            .first()
        )

        if not last or last.price_dkk != item["price"]:
            history = PriceHistory(
                beer_id=beer.id,
                price_dkk=item["price"],
                shop_name=item["shop_name"],
            )
            db.add(history)

        # 🔥 alerts
        alerts = db.query(PriceAlert).filter(
            PriceAlert.beer_id == beer.id,
            PriceAlert.active == True
        ).all()

        for alert in alerts:
            if item["price"] <= alert.target_price:
                print(f"🔥 ALERT: {beer.name} now {item['price']} kr")
                alert.active = False

    db.commit()