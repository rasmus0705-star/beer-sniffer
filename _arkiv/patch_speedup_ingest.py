import shutil, sys

PATH = "app/services/ingest.py"
shutil.copy(PATH, PATH + ".bak")
print(f"💾 Backup gemt: {PATH}.bak")

with open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

# --- Ændring 1: preload seneste historik-priser FØR løkken ---
anchor1 = "    new_prices = []\n    new_histories = []\n"
preload = """    new_prices = []
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
"""

if anchor1 not in src:
    print("❌ Fandt ikke ankeret for Ændring 1 (new_prices/new_histories). Stopper.")
    sys.exit(1)
if src.count(anchor1) != 1:
    print(f"⚠️  Ankeret for Ændring 1 findes {src.count(anchor1)} gange — forventede 1. Stopper.")
    sys.exit(1)
src = src.replace(anchor1, preload, 1)

# --- Ændring 2: erstat per-øl-forespørgslen med dict-opslag ---
anchor2 = """        last = (
            db.query(PriceHistory)
            .filter(
                PriceHistory.beer_id == beer.id,
                PriceHistory.shop_name == item["shop_name"]
            )
            .order_by(PriceHistory.created_at.desc())
            .first()
        )

        if not last or last.price_dkk != item["price"]:"""

replacement2 = """        last_price = latest_hist.get((beer.id, item["shop_name"]))

        if last_price is None or last_price != item["price"]:"""

if anchor2 not in src:
    print("❌ Fandt ikke ankeret for Ændring 2 (per-øl query). Stopper — ingen ændringer gemt.")
    sys.exit(1)
src = src.replace(anchor2, replacement2, 1)

# opdater ogsaa latest_hist undervejs, saa dubletter i SAMME koersel ikke logges dobbelt
anchor3 = """            new_histories.append(PriceHistory(
                beer_id=beer.id,
                price_dkk=item["price"],
                shop_name=item["shop_name"],
            ))"""
replacement3 = """            new_histories.append(PriceHistory(
                beer_id=beer.id,
                price_dkk=item["price"],
                shop_name=item["shop_name"],
            ))
            latest_hist[(beer.id, item["shop_name"])] = item["price"]"""

if anchor3 in src:
    src = src.replace(anchor3, replacement3, 1)
    print("✅ Ændring 3 (dedup i samme koersel) anvendt")
else:
    print("⚠️  Kunne ikke tilfoeje dedup-opdatering — ikke kritisk, men sig til.")

with open(PATH, "w", encoding="utf-8") as f:
    f.write(src)

print("✅ Ændring 1 (preload) anvendt")
print("✅ Ændring 2 (dict-opslag) anvendt")
print("\n🎯 Faerdig. Per-oel DB-forespoergslen er erstattet af et hukommelses-opslag.")