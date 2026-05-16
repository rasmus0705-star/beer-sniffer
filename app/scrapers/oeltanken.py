import requests
import re
from app.utils.detect_type import detect_type


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
}


def scrape_oeltanken():
    items = []
    page = 1

    skip_keywords = [
        "glas", "glass", "krus", "opener", "trøje", "t-shirt",
        "cap", "hat", "gave", "gavekort", "merchandise", "sodavand",
        "juice", "spiritus", "whisky", "gin", "rom", "vin", "wine",
        "snack", "chips", "nødder", "tilbehør", "renser", "brush",
        "børste", "tap", "pumpe", "slange", "pant", "ølglas",
        "chokolade", "chocolate", "fustage", "fadøl", "keg", "anker"
    ]

    while True:
        url = f"https://oltanken.dk/products.json?limit=250&page={page}"

        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            data = response.json()
        except Exception as e:
            print(f"❌ Øltanken fejl på side {page}: {e}")
            break

        products = data.get("products", [])

        if not products:
            break

        for product in products:

            name = product.get("title")

            if not name:
                continue

            lower_name = name.lower()

            if any(kw in lower_name for kw in skip_keywords):
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
                try:
                    old_price = float(old_price)
                except:
                    old_price = None

            discount = None

            if old_price and old_price > price:
                discount = round(
                    ((old_price - price) / old_price) * 100,
                    1
                )

            handle = product.get("handle")

            product_url = (
                f"https://oltanken.dk/products/{handle}"
            )

            image = None

            images = product.get("images", [])

            if images and len(images) > 0:
                image = images[0].get("src")

            # VOLUME
            volume = None

            text_to_scan = f"""
                {name}
                {product.get("body_html", "")}
                {' '.join(product.get("tags", []))}
            """

            volume_match = re.search(
                r"(\d+(?:[.,]\d+)?)\s*(cl|ml|l)\b",
                text_to_scan.lower()
            )

            if volume_match:

                val = float(
                    volume_match.group(1).replace(",", ".")
                )

                unit = volume_match.group(2)

                if unit == "l":
                    val = val * 100

                elif unit == "ml":
                    val = val / 10

                if val <= 75:
                    volume = val

            else:
                if "33cl" in lower_name:
                    volume = 33

                elif "44cl" in lower_name:
                    volume = 44

                elif "50cl" in lower_name:
                    volume = 50

            # ABV
            abv = None

            abv_match = re.search(
                r"(\d+(?:[.,]\d+)?)\s*%",
                text_to_scan
            )

            if abv_match:
                try:
                    abv = float(
                        abv_match.group(1).replace(",", ".")
                    )
                except:
                    pass

            # UNTAPPD
            untappd_url = None
            untappd_id = None

            body_html = product.get("body_html", "")

            untappd_match = re.search(
                r'https:\/\/untappd\.com\/b\/[^\/]+\/(\d+)',
                body_html
            )

            if untappd_match:
                untappd_id = untappd_match.group(1)

                untappd_url_match = re.search(
                    r'https:\/\/untappd\.com\/b\/[^"]+',
                    body_html
                )

                if untappd_url_match:
                    untappd_url = untappd_url_match.group(0)

            # TYPE
            beer_type = detect_type(name)

            if not beer_type:
                beer_type = detect_type(
                    " ".join(product.get("tags", []))
                )

            # BREWERY
            brewery = None

            if " - " in name:
                brewery = name.split(" - ")[0].strip()

            if not brewery:
                brewery = product.get("vendor")

            # ITEM
            item = {
                "external_id": product.get("id"),
                "name": name,
                "price": price,
                "old_price": old_price,
                "discount_pct": discount,
                "url": product_url,
                "shop_name": "Øltanken",
                "volume_cl": volume,
                "abv": abv,
                "image": image,
                "type": beer_type,
                "brewery": brewery,
                "category": "øl",
                "sku": variant.get("sku"),
                "available": variant.get("available"),
                "untappd_url": untappd_url,
                "untappd_id": untappd_id,
                "tags": product.get("tags", []),
            }

            items.append(item)

        print(
            f"📦 Øltanken side {page}: "
            f"{len(products)} produkter hentet"
        )

        page += 1

    return items


if __name__ == "__main__":
    items = scrape_oeltanken()
    print(f"\n✅ Total: {len(items)} items")
    if items:
        print(f"\nFørste item:")
        for k, v in items[0].items():
            print(f"  {k}: {v}")