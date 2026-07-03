from sqlalchemy.orm import Session

from app.models import Beer, Price, PriceHistory, PriceAlert
from app.utils.normalize import normalize_name
from app.utils.slugify import slugify, resolve_collisions, is_valid_brewery, is_valid_brewery
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


def find_best_match(item_norm, item_fp, item_vol, item_abv, item_brewery, item_name, candidate_beers):
    """
    Robust matching:
    - 4 hårde gates: stil, volume, ABV, bryggeri
    - Mandatory: navnene skal dele mindst ét meningsfuldt ord
    - Dynamisk threshold: jo mere data der mangler, jo højere score kræves
    """
    best_score = 0.0
    best_beer = None
    best_threshold = MATCH_THRESHOLD

    for beer in candidate_beers:
        beer_fp = style_fingerprint(beer.name)

        # Hård gate 1: stilarter
        if not styles_compatible(item_fp, beer_fp):
            continue

        # Hård gate 2: volume
        if not volumes_compatible(item_vol, beer.volume_cl):
            continue

        # Hård gate 3: ABV
        if not abv_compatible(item_abv, beer.abv):
            continue

        # Hård gate 4: bryggeri
        if not breweries_compatible(item_brewery, beer.brewery, item_name, beer.name):
            continue

        # Mandatory: navnene skal dele meningsfulde ord
        if not has_meaningful_overlap(item_name, beer.name):
            continue

        beer_norm = normalize_for_matching(beer.name)
        score = similarity_score(
            item_norm, beer_norm,
            item_abv, beer.abv,
            item_brewery, beer.brewery,
            item_fp, beer_fp,
        )

        # Dynamisk threshold afhængigt af hvor meget data vi har
        threshold = required_threshold(
            item_abv, beer.abv,
            item_vol, beer.volume_cl,
            item_brewery, beer.brewery,
        )

        if score > best_score:
            best_score = score
            best_beer = beer
            best_threshold = threshold

    if best_beer and best_score >= best_threshold:
        return best_beer

    return None


def ingest_batch(db: Session, items: list[dict]):
    if not items:
        return

    before_count = len(items)
    items = [
        it for it in items
        if it.get("name")
        and it.get("price") is not None
        and it["price"] > 5
    ]
    filtered_count = before_count - len(items)
    if filtered_count > 0:
        print(f"⚠️ Filtreret {filtered_count} ugyldige items væk (0-pris eller manglende navn)")

    if not items:
        return

    all_beers = db.query(Beer).all()

    existing_slugs = {b.slug for b in all_beers if b.slug}

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

    # PERF: hent seneste historik-pris pr. (beer_id, shop_name) i EN forespørgsel
    # i stedet for en pr. øl inde i løkken (fjerner ~2600 netvaerks-rundture)
    _hist_rows = (
        db.query(PriceHistory.beer_id, PriceHistory.shop_name, PriceHistory.price_dkk)
        .order_by(PriceHistory.beer_id, PriceHistory.shop_name, PriceHistory.created_at.desc())
        .all()
    )
    latest_hist = {}
    for _bid, _shop, _price in _hist_rows:
        key = (_bid, _shop)
        if key not in latest_hist:          # foerste = nyeste pga. desc-sortering
            latest_hist[key] = _price

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
            new_slug = slugify(item_name, item_brewery)
            new_slug = resolve_collisions(new_slug, existing_slugs)
            existing_slugs.add(new_slug)

            beer = Beer(
                name=item_name,
                normalized_name=normalize_name(item_name),
                brewery=item_brewery,
                type=item.get("type"),
                volume_cl=item_vol,
                abv=item_abv,
                image=item.get("image"),
                slug=new_slug,
                description=item.get("description"),
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
        # Opgradér til en bedre (længere) beskrivelse, hvis en findes —
        # i modsætning til de andre felter ovenfor vil vi altid have den
        # bedste tekst, ikke bare "udfyld hvis tom".
        _new_desc = item.get("description")
        if _new_desc and (not beer.description or len(_new_desc) > len(beer.description)):
            beer.description = _new_desc
        # Udfyld hvis tomt, ELLER opgradér hvis den nuværende værdi er
        # ugyldig (shop-navn/dato) og den nye rent faktisk er gyldig —
        # retter historiske fejl automatisk over de kommende dage.
        if item_brewery and (
            not beer.brewery
            or (not is_valid_brewery(beer.brewery) and is_valid_brewery(item_brewery))
        ):
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

        last_price = latest_hist.get((beer.id, item["shop_name"]))

        if last_price is None or last_price != item["price"]:
            new_histories.append(PriceHistory(
                beer_id=beer.id,
                price_dkk=item["price"],
                shop_name=item["shop_name"],
            ))
            latest_hist[(beer.id, item["shop_name"])] = item["price"]

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
        clear_cache = lambda: None  # statisk pipeline - ingen server-cache at rydde (FastAPI-routers fjernet)
        clear_cache()
        print("🧹 Cache ryddet")
    except Exception as e:
        print(f"⚠️ Kunne ikke rydde cache: {e}")

    print(f"✅ Ingest færdig — {len(items)} øl behandlet")