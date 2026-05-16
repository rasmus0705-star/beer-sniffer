import requests
import re
from app.utils.detect_type import detect_type


HEADERS = {"User-Agent": "Mozilla/5.0"}


def scrape_beershoppen():
    items = []
    page = 1

    allowed_types = {'Beer'}

    skip_keywords = [
        "glas", "glass", "krus", "opener", "trøje", "t-shirt",
        "cap", "hat", "gave", "gavekort", "merchandise", "sodavand",
        "juice", "spiritus", "whisky", "gin", "rom", "vin", "wine",
        "snack", "chips", "nødder", "tilbehør", "renser", "brush",
        "børste", "tap", "pumpe", "slange", "pant", "ølglas",
        "chokolade", "chocolate", "fustage", "fadøl", "keg", "anker",
        "abonnement", "subscription", "giftbox", "gift box",
        "diverse", "mystery"
    ]

    while True:
        url = f"https://beershoppen.dk/products.json?limit=250&page={page}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            data = response.json()
        except Exception as e:
            print(f"❌ Beershoppen fejl på side {page}: {e}")
            break

        products = data.get("products", [])
        if not products:
            break

        for product in products:
            name = product.get("title")
            if not name:
                continue

            if any(kw in name.lower() for kw in skip_keywords):
                continue

            product_type = product.get("product_type", "")
            if product_type not in allowed_types:
                continue

            variants = product.get("variants", [])
            if not variants:
                continue

            variant = variants[0]

            if not variant.get("available"):
                continue

            try:
                price = float(variant.get("price"))
            except:
                continue

            old_price = variant.get("compare_at_price")
            if old_price:
                old_price = float(old_price)

            discount = None
            if old_price and old_price > price:
                discount = round((old_price - price) / old_price * 100, 1)

            handle = product.get("handle")
            product_url = f"https://beershoppen.dk/products/{handle}"

            image = None
            if product.get("image") and product["image"]:
                image = product["image"].get("src")
            elif product.get("images") and len(product["images"]) > 0:
                image = product["images"][0].get("src")

            # Filtrer store volumener fra
            volume = None
            is_smagekasse = any(kw in name.lower() for kw in [
                "smagekasse", "smagekasser", "smagesæt", "smagskasse", "smagssæt", "sæt", "mix", "bundle", "pakke"
            ]) or bool(re.search(r"\d+\s*stk", name.lower()))
            if not is_smagekasse:
                volume_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(cl|ml|l)\b", name.lower())
                if volume_match:
                    val = float(volume_match.group(1).replace(",", "."))
                    unit = volume_match.group(2)
                    if unit == "l":
                        val = val * 100
                    elif unit == "ml":
                        val = val / 10
                    if val > 75:
                        continue
                    volume = val
                else:
                    if "33cl" in name.lower() or "33 cl" in name.lower():
                        volume = 33
                    elif "44cl" in name.lower() or "44 cl" in name.lower():
                        volume = 44
                    elif "50cl" in name.lower() or "50 cl" in name.lower():
                        volume = 50

            abv = None
            if name:
                match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", name)
                if match:
                    abv = float(match.group(1).replace(",", "."))

            item = {
                "name": name,
                "price": price,
                "old_price": old_price,
                "discount_pct": discount,
                "url": product_url,
                "shop_name": "Beershoppen",
                "volume_cl": volume,
                "abv": abv,
                "image": image,
                "type": detect_type(name) or (product_type if product_type else None),
                "brewery": product.get("vendor") or None,
                "category": "smagekasse" if is_smagekasse else "øl",
            }

            items.append(item)

        print(f"📦 Beershoppen side {page}: {len(products)} produkter hentet")
        page += 1

    return items


if __name__ == "__main__":
    items = scrape_beershoppen()
    print(f"\n✅ Total: {len(items)} items")