import requests
import re
from app.utils.detect_type import detect_type


def scrape_agoodcase():
    items = []
    page = 1

    allowed_types = {'', 'Øl', 'Smagekasse'}

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

    bulk_keywords = [
        r"\b(\d+)\s*stk\.?\b",
        r"\b(\d+)\s*pack\b",
        r"\b(\d+)\s*pak\b",
        r"\bx\s*(\d+)\b",
        r"\b(\d+)\s*x\b",
    ]

    def parse_bulk_qty(title):
        if not title:
            return None
        t = title.lower().strip()
        for pattern in bulk_keywords:
            m = re.search(pattern, t)
            if m:
                try:
                    qty = int(m.group(1))
                    if 2 <= qty <= 48:
                        return qty
                except:
                    pass
        return None

    while True:
        url = f"https://agoodcase.dk/products.json?limit=250&page={page}"
        response = requests.get(url)
        try:
            data = response.json()
        except Exception:
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

            single_variant = None
            bulk_variants = []

            for v in variants:
                if not v.get("available"):
                    continue
                try:
                    v_price = float(v.get("price", 0))
                except:
                    continue
                if v_price <= 0:
                    continue

                v_title = v.get("title", "")
                qty = parse_bulk_qty(v_title)

                if qty and qty > 1:
                    bulk_variants.append({
                        "qty": qty,
                        "price_per_unit": round(v_price / qty, 2),
                        "total_price": v_price,
                        "variant_title": v_title,
                        "variant": v,
                    })
                else:
                    if single_variant is None:
                        single_variant = v

            # Hvis ingen enkeltpris findes, brug billigste bulk-variant og vis pris per stk
            bulk_only = False
            if single_variant is None and bulk_variants:
                bulk_variants.sort(key=lambda x: x["price_per_unit"])
                cheapest_bulk = bulk_variants[0]
                single_variant = cheapest_bulk["variant"]
                bulk_only = True
                bulk_qty = cheapest_bulk["qty"]
                bulk_price_per_unit = cheapest_bulk["price_per_unit"]
                bulk_total = cheapest_bulk["total_price"]

            if single_variant is None:
                continue

            try:
                if bulk_only:
                    # Vis pris per stk og tilføj antal til navn
                    price = bulk_price_per_unit
                    display_name = f"{name} ({bulk_qty} stk.)"
                    old_price_raw = single_variant.get("compare_at_price")
                    old_price = round(float(old_price_raw) / bulk_qty, 2) if old_price_raw else None
                else:
                    price = float(single_variant.get("price"))
                    display_name = name
                    old_price_raw = single_variant.get("compare_at_price")
                    old_price = float(old_price_raw) if old_price_raw else None
            except:
                continue

            discount = None
            if old_price and old_price > price:
                discount = round((old_price - price) / old_price * 100, 1)

            handle = product.get("handle")
            product_url = f"https://agoodcase.dk/products/{handle}"

            image = None
            if product.get("image") and product["image"]:
                image = product["image"].get("src")
            elif product.get("images") and len(product["images"]) > 0:
                image = product["images"][0].get("src")

            volume = None
            is_smagekasse = any(kw in name.lower() for kw in [
                "smagekasse", "smagekasser", "smagesæt", "smagskasse", "smagssæt", "sæt", "mix", "bundle", "pakke"
            ])
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
                    if "33cl" in name.lower():
                        volume = 33
                    elif "44cl" in name.lower():
                        volume = 44
                    elif "50cl" in name.lower():
                        volume = 50

            abv = None
            if name:
                match = re.search(r"(\d+[.,]\d+)%", name)
                if match:
                    abv = float(match.group(1).replace(",", "."))

            # Fjern variant info fra bulk_variants (ikke serialiserbar)
            clean_bulk = []
            for b in bulk_variants:
                clean_bulk.append({
                    "qty": b["qty"],
                    "price_per_unit": b["price_per_unit"],
                    "total_price": b["total_price"],
                    "variant_title": b["variant_title"],
                })
            clean_bulk.sort(key=lambda x: x["qty"])

            item = {
                "name": display_name,
                "price": price,
                "old_price": old_price,
                "discount_pct": discount,
                "url": product_url,
                "shop_name": "A Good Case",
                "volume_cl": volume,
                "abv": abv,
                "image": image,
                "type": detect_type(name) or (product_type if product_type else None),
                "brewery": product.get("vendor") or None,
                "category": "smagekasse" if is_smagekasse else "øl",
                "bulk_discounts": clean_bulk if clean_bulk else None,
            }

            items.append(item)

        print(f"📦 Side {page}: {len(products)} produkter hentet")
        page += 1

    return items