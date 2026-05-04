import requests
import re
from app.utils.detect_type import detect_type


def scrape_bestofbeers():
    items = []
    page = 1
    per_page = 100

    skip_keywords = [
        "glas", "glass", "krus", "opener", "trøje", "t-shirt",
        "cap", "hat", "gave", "gavekort", "merchandise", "sodavand",
        "juice", "spiritus", "whisky", "gin", "rom", "vin", "wine",
        "snack", "chips", "nødder", "tilbehør", "renser",
        "chokolade", "chocolate", "fustage", "fadøl", "keg", "anker",
        "abonnement", "pant", "gavekort", "kort til modtageren", "kort til", "gift card", "geschenkkarte"
    ]

    while True:
        url = f"https://bestofbeers.dk/wp-json/wc/store/v1/products?per_page={per_page}&page={page}&stock_status=instock"
        response = requests.get(url, timeout=15)

        if response.status_code != 200:
            break

        products = response.json()
        if not products:
            break

        for product in products:
            name = product.get("name") or ''
            if not name:
                continue

            if any(kw in name.lower() for kw in skip_keywords):
                continue

            # Pris er i øre
            try:
                prices_data = product.get("prices", {})
                price = int(prices_data.get("price", 0)) / 100
                regular_price = int(prices_data.get("regular_price", 0)) / 100
                sale_price = int(prices_data.get("sale_price", 0)) / 100
            except:
                continue

            if price <= 0:
                continue

            old_price = None
            discount = None
            if regular_price > price:
                old_price = regular_price
                discount = round((regular_price - price) / regular_price * 100, 1)

            # URL
            product_url = product.get("permalink") or ''

            # Billede
            images = product.get("images", [])
            image = images[0].get("src") if images else None

            # Volumen
            volume = None
            name_lower = name.lower()
            vol_match = re.search(r'(\d+[.,]?\d*)\s*(cl|ml|l)\.?', name_lower)
            if vol_match:
                val = float(vol_match.group(1).replace(',', '.'))
                unit = vol_match.group(2)
                if unit == 'l':
                    val = val * 100
                elif unit == 'ml':
                    val = val / 10
                if val > 75:
                    continue
                volume = val

            # ABV
            abv = None
            abv_match = re.search(r'(\d+[.,]\d+)\s*%', name)
            if abv_match:
                abv = float(abv_match.group(1).replace(',', '.'))

            is_smagekasse = any(kw in name.lower() for kw in [
                "smagekasse", "smagesæt", "smagskasse", "mix", "bundle", "pakke"
            ]) or bool(re.search(r'\d+\s*stk', name.lower()))

            item = {
                "name": name,
                "price": price,
                "old_price": old_price,
                "discount_pct": discount,
                "url": product_url,
                "shop_name": "Best of Beers",
                "volume_cl": volume,
                "abv": abv,
                "image": image,
                "type": detect_type(name),
                "brewery": None,
                "category": "smagekasse" if is_smagekasse else "øl",
            }

            items.append(item)

        print(f"📦 Side {page}: {len(products)} produkter hentet")
        page += 1

        # Stop hvis vi har hentet alle
        if len(products) < per_page:
            break

    return items