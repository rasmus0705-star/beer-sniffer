import requests
import time
import re
import html
from app.utils.detect_type import detect_type
from app.utils.slugify import is_valid_brewery
from app.utils.slugify import is_valid_brewery
from app.utils.description import clean_description

# Drikbeer.com er en Shopify-shop (niche US/belgisk import). Vol + ABV ligger i
# body_html ("ABV: 13.0%", "Size: 330ML"), saa ingen sidehentning/cache noedvendig.
# Forskelle fra beermatch.py:
#   - vendor ER bryggeriet (bruges som primaer bryggeri-kilde)
#   - body-labels er engelske: Style: / ABV: / Size:
#   - product_type = "Beer" findes og bruges til at skippe ikke-oel
#   - multipak (6-pack osv.) markeres som smagekasse (per-flaske-pris er en
#     separat opgave, jf. multipak_prompt.md)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
}

BASE = "https://drikbeer.com"


def _clean(text):
    """Fjern HTML-tags og unescape entiteter. Returner ' '-joinet tekst."""
    if not text:
        return ""
    t = re.sub(r'<[^>]+>', ' ', text)
    t = html.unescape(t)
    return re.sub(r'\s+', ' ', t).strip()


def _parse_abv(text):
    """ABV fra Drikbeer-body. Foretrukket: 'ABV: 13.0%'. Fallback: 'Alcohol:' / generisk."""
    if not text:
        return None
    t = _clean(text)
    m = (
        re.search(r'abv\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*%', t, re.IGNORECASE)
        or re.search(r'alcohol\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*%', t, re.IGNORECASE)
        or re.search(r'(\d+(?:[.,]\d+)?)\s*%', t)
    )
    if m:
        try:
            val = float(m.group(1).replace(',', '.'))
            if 0 < val <= 25:
                return val
        except ValueError:
            pass
    return None


def _parse_volume(text):
    """Volumen i cl. Foretrukket: 'Size: 330ML'. Fallback: generisk 'NN ml/cl/l'."""
    if not text:
        return None
    t = _clean(text).lower()
    m = re.search(r'size\s*[:\-]?\s*(\d+(?:[.,]\d+)?)\s*(ml|cl|l)\b', t)
    if not m:
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*(ml|cl|l)\b', t)
    if m:
        try:
            val = float(m.group(1).replace(',', '.'))
        except ValueError:
            return None
        unit = m.group(2)
        if unit == 'l':
            val *= 100
        elif unit == 'ml':
            val /= 10
        if 0 < val <= 75:
            return val
    return None


def _parse_style_line(body_html):
    """Traek 'Style: <...>' (eller 'Type:') ud af body_html til detect_type."""
    t = _clean(body_html)
    m = re.search(r'(?:style|type)\s*[:\-]?\s*([^.\n|]+)', t, re.IGNORECASE)
    if not m:
        return ""
    # Klip ved naeste label (ABV/Size/Alcohol) saa kun selve stilen returneres
    val = re.split(r'\b(?:abv|size|alcohol)\b', m.group(1), flags=re.IGNORECASE)[0]
    return val.strip()


def scrape_drikbeer():
    items = []
    page = 1

    # Ikke-oel-produkttyper (Shopify product_type)
    non_beer_types = {
        "gift card", "merch", "merchandise", "apparel", "glassware",
        "accessories", "clothing",
    }

    # Ikke-oel via titel (sikkerhedsnet udover product_type)
    skip_keywords = [
        "gift card", "gavekort", "merch", "t-shirt", "tr\u00f8je",
        "glassware", "glas", "tote", "sticker", "hoodie", "cap ",
        "subscription", "abonnement",
    ]

    # Multipak / pakker -> smagekasse (per-flaske-pris haandteres separat)
    pack_keywords = [
        "smagekasse", "mixed", "mix pack", "bundle", "case", "gift box",
        "pakke", "pakken",
    ]

    while True:
        url = f"{BASE}/products.json?limit=250&page={page}"
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            data = response.json()
        except Exception as e:
            print(f"\u274c Drikbeer fejl paa side {page}: {e}")
            break

        products = data.get("products", [])
        if not products:
            break

        for product in products:
            name = product.get("title")
            if not name:
                continue

            name_lower = name.lower()

            ptype = (product.get("product_type") or "").strip().lower()
            if ptype in non_beer_types:
                continue
            if any(kw in name_lower for kw in skip_keywords):
                continue

            variants = product.get("variants", [])
            if not variants:
                continue

            variant = variants[0]
            if not variant.get("available"):
                continue

            try:
                price = float(variant.get("price"))
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue

            old_price = variant.get("compare_at_price")
            if old_price:
                try:
                    old_price = float(old_price)
                except (TypeError, ValueError):
                    old_price = None

            discount = None
            if old_price and old_price > price:
                discount = round(((old_price - price) / old_price) * 100, 1)

            handle = product.get("handle")
            product_url = f"{BASE}/products/{handle}"

            images = product.get("images", [])
            image = images[0].get("src") if images else None

            body_html = product.get("body_html", "")
            tags = product.get("tags", [])
            tags_lower = [str(t).lower() for t in tags]

            # Multipak? (tag '6-pack', '(N-pack)' i navn, 'N stk', case/mixed ...)
            is_pack = (
                any(kw in name_lower for kw in pack_keywords)
                or any(re.search(r'\d+\s*-?\s*pack', t) for t in tags_lower)
                or bool(re.search(r'\d+\s*-?\s*pack', name_lower))
                or bool(re.search(r'\d+\s*stk', name_lower))
            )

            # Vol/ABV kun for enkeltoel
            volume = None
            abv = None
            if not is_pack:
                volume = _parse_volume(body_html) or _parse_volume(name)
                abv = _parse_abv(body_html) or _parse_abv(name)

            # Bryggeri: vendor er normalt korrekt hos Drikbeer, men valider
            # alligevel — for en sikkerheds skyld mod samme type shop-navn/
            # dato-kontaminering set hos andre Shopify-butikker.
            _vendor = product.get("vendor") or None
            brewery = _vendor if is_valid_brewery(_vendor) else None
            if not brewery and ' - ' in name:
                brewery = name.split(' - ')[0].strip()

            # Type: navn -> Style:-linjen -> tags
            beer_type = (
                detect_type(name)
                or detect_type(_parse_style_line(body_html))
                or detect_type(' '.join(str(t) for t in tags))
            )

            item = {
                "external_id": product.get("id"),
                "name": name,
                "price": price,
                "old_price": old_price,
                "discount_pct": discount,
                "url": product_url,
                "shop_name": "Drikbeer",
                "volume_cl": volume,
                "grams": variant.get("grams"),
                "abv": abv,
                "image": image,
                "type": beer_type,
                "brewery": brewery,
                "category": "smagekasse" if is_pack else "\u00f8l",
                "sku": variant.get("sku"),
                "available": variant.get("available"),
                "untappd_url": None,
                "untappd_id": None,
                "tags": tags,
                "description": clean_description(body_html),
            }

            items.append(item)

        print(f"\U0001f4e6 Drikbeer side {page}: {len(products)} produkter hentet")
        page += 1

        time.sleep(1.0)
    return items


if __name__ == "__main__":
    items = scrape_drikbeer()
    print(f"\n\u2705 Total: {len(items)} items")
    with_brewery = sum(1 for it in items if it.get("brewery"))
    with_volume = sum(1 for it in items if it.get("volume_cl"))
    with_abv = sum(1 for it in items if it.get("abv"))
    smagekasser = sum(1 for it in items if it.get("category") == "smagekasse")
    print(f"Med bryggeri: {with_brewery}/{len(items)}")
    print(f"Med volumen:  {with_volume}/{len(items)}")
    print(f"Med ABV:      {with_abv}/{len(items)}")
    print(f"Pakker/multipak: {smagekasser}")
    if items:
        print(f"\nFoerste enkeltoel:")
        first = next((it for it in items if it.get("category") == "\u00f8l"), items[0])
        for k, v in first.items():
            print(f"  {k}: {v}")