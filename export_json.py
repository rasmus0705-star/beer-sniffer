import json
from datetime import datetime
from app.scrapers.brygshoppen import scrape_brygshoppen
from app.scrapers.agoodcase import scrape_agoodcase
from app.scrapers.beershoppen import scrape_beershoppen
from app.scrapers.beerme import scrape_beerme
from app.scrapers.oeltanken import scrape_oeltanken
from app.scrapers.bestofbeers import scrape_bestofbeers
from app.utils.normalize import normalize_name
from rapidfuzz import fuzz


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


def find_match(normalized, volume, abv, grouped, shop_name=""):
    best_score = 0
    best_key = None

    for key, beer in grouped.items():
        # Spring volumen check hvis én af dem mangler volumen
        if volume is not None and beer["volume_cl"] is not None:
            if beer["volume_cl"] != volume:
                continue

        score = fuzz.token_sort_ratio(normalized, beer["normalized_name"])

        if abv is not None and beer.get("abv") is not None:
            if abs(abv - beer["abv"]) < 0.2:
                score += 8
            elif abs(abv - beer["abv"]) > 1.0:
                score -= 10

        if score > best_score:
            best_score = score
            best_key = key

    threshold = 72 if shop_name == "Beer Me" else 78
    if best_score >= threshold:
        return best_key
    return None


grouped = {}
counter = 0

for item in items:
    normalized = normalize_name(item["name"])
    volume = item.get("volume_cl")
    abv = item.get("abv")
    shop_name = item.get("shop_name", "")
    match_key = find_match(normalized, volume, abv, grouped, shop_name)

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
            if not grouped[match_key]["image"] and item.get("image"):
                grouped[match_key]["image"] = item["image"]
            if not grouped[match_key]["abv"] and abv:
                grouped[match_key]["abv"] = abv
            if not grouped[match_key]["volume_cl"] and volume:
                grouped[match_key]["volume_cl"] = volume
            if not grouped[match_key]["type"] and item.get("type"):
                grouped[match_key]["type"] = item["type"]
        else:
            key = f"beer_{counter}"
            counter += 1
            grouped[key] = {
                "name": item["name"],
                "normalized_name": normalized,
                "type": item.get("type"),
                "brewery": item.get("brewery"),
                "volume_cl": volume,
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
    else:
        key = f"beer_{counter}"
        counter += 1
        grouped[key] = {
            "name": item["name"],
            "normalized_name": normalized,
            "type": item.get("type"),
            "brewery": item.get("brewery"),
            "volume_cl": volume,
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

beers = []
for key, beer in grouped.items():
    prices = beer["prices"]
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