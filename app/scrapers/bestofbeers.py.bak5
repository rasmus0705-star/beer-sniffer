import requests
import re
import html
from app.utils.detect_type import detect_type


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
}

_DASH_RE = re.compile(r'\s*[\u2013\u2014]\s*')


def _clean_name(raw):
    """Decode HTML entities og normaliser tankestreger til ' – '."""
    return _DASH_RE.sub(' \u2013 ', html.unescape(raw or '')).strip()


def _extract_brewery(name):
    """
    Best of Beers-titler: 'Bryggeri – Produkt – Stil – volumen – ABV'
    Første segment er bryggeriet.
    """
    parts = [p.strip() for p in name.split(' \u2013 ') if p.strip()]
    if not parts:
        return None
    candidate = parts[0]
    if re.search(r'\d+[.,]?\d*\s*(l|cl|ml|%)\.?$', candidate.lower()):
        return None
    return candidate


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
        "abonnement", "pant", "kort til modtageren", "kort til",
        "gift card", "geschenkkarte",
        # Merchandise / tilbehør (ikke drikkevarer)
        "drikkehorn", "horn med holder", "bottle opener", "oplukker",
        "køletaske", "termo", "kølebox",
        "riedel", "forsendelse", "fragt",
    ]

    while True:
        url = f"https://bestofbeers.dk/wp-json/wc/store/v1/products?per_page={per_page}&page={page}&stock_status=instock"
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
        except Exception as e:
            print(f"❌ Best of Beers fejl på side {page}: {e}")
            break

        if response.status_code != 200:
            break

        try:
            products = response.json()
        except Exception as e:
            print(f"❌ Best of Beers JSON fejl på side {page}: {e}")
            break

        if not products:
            break

        for product in products:
            raw_name = product.get("name") or ''
            if not raw_name:
                continue

            # Rens HTML-entities og normaliser separatorer
            name = _clean_name(raw_name)

            if any(kw in name.lower() for kw in skip_keywords):
                continue

            try:
                prices_data = product.get("prices", {})
                price = int(prices_data.get("price", 0)) / 100
                regular_price = int(prices_data.get("regular_price", 0)) / 100
            except:
                continue

            if price <= 0:
                continue

            old_price = None
            discount = None
            if regular_price > price:
                old_price = regular_price
                discount = round((regular_price - price) / regular_price * 100, 1)

            product_url = product.get("permalink") or ''
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
            abv_match = re.search(r'(\d+(?:[.,]\d+)?)\s*%', name)
            if abv_match:
                abv = float(abv_match.group(1).replace(',', '.'))

            # Bryggeri fra titelstruktur
            brewery = _extract_brewery(name)

            is_smagekasse = any(kw in name_lower for kw in [
                "smagekasse", "smagesæt", "smagskasse", "mix", "bundle", "pakke"
            ]) or bool(re.search(r'\d+\s*stk', name_lower))

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
                "brewery": brewery,
                "category": "smagekasse" if is_smagekasse else "øl",
            }

            items.append(item)

        print(f"📦 Best of Beers side {page}: {len(products)} produkter hentet")
        page += 1

        if len(products) < per_page:
            break

    return items


if __name__ == "__main__":
    items = scrape_bestofbeers()
    print(f"\n✅ Total: {len(items)} items")
    with_brewery = sum(1 for it in items if it.get("brewery"))
    with_volume = sum(1 for it in items if it.get("volume_cl"))
    print(f"Med bryggeri: {with_brewery}/{len(items)}")
    print(f"Med volumen:  {with_volume}/{len(items)}")