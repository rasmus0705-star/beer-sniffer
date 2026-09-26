"""
ol2go.py — Scraper til ØL2GO (ol2go.dk) via WooCommerce Store API.
Returnerer en liste af dicts i BeerSniffers standardformat.
"""
from html import unescape
import re
import requests

SHOP_NAME = "ØL2GO"
SHOP_URL = "https://ol2go.dk"
SHOP_SHIPPING = {'price': 49, 'freeOver': 599, 'note': 'Levering med GLS'}


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://ol2go.dk/",
    "Origin": "https://ol2go.dk",
}

BASE_URL = "https://ol2go.dk/wp-json/wc/store/v1/products"

# Kategorier der IKKE er øl
SKIP_CATEGORIES = {
    "spiritus", "cider", "likør", "likoer", "most", "most og sodavand",
    "chips", "glas", "gaveæsker og indpakning", "gaveaesker-og-indpakning",
    "ølsmagning", "oelsmagning", "diverse",
}

SKIP_KEYWORDS = [
    "glas", "glass", "krus", "opener", "trøje", "t-shirt", "cap", "hat",
    "gave", "gavekort", "merchandise", "sodavand", "juice", "spiritus",
    "whisky", "gin", "rom ", "vin ", "wine", "snack", "chips", "nødder",
    "tilbehør", "fadølsanlæg", "ølsmagning", "co2",
    "discovery box", "discoverybox", "smagekasse", "smagskasse",
    "tasting box", "gift box", "bundle",
]


def _parse_volume(name, weight_g):
    """Forsøg at finde volumen i cl fra navn eller vægt."""
    # Prøv eksplicit i navnet
    m = re.search(r"(\d+)\s*cl\b", name, re.IGNORECASE)
    if m:
        return int(m.group(1))

    m = re.search(r"(\d+)\s*ml\b", name, re.IGNORECASE)
    if m:
        return int(m.group(1)) / 10

    # Gæt fra vægt (inkl. emballage): ~550g ≈ 33cl dåse, ~700-750g ≈ 33cl flaske
    if weight_g:
        try:
            w = float(weight_g)
            if w <= 600:
                return 33
            elif w <= 900:
                return 33
            elif w <= 1200:
                return 50
            elif w <= 1800:
                return 75
        except (ValueError, TypeError):
            pass

    return None


def _parse_abv(name, description):
    """Forsøg at finde alkoholprocent fra navn eller beskrivelse."""
    for text in [name, description]:
        if not text:
            continue
        m = re.search(r"(\d+[.,]\d+)\s*%", text)
        if m:
            val = float(m.group(1).replace(",", "."))
            if 0 < val <= 30:
                return val
    return None


def _map_category(categories, tags):
    """Map WooCommerce-kategorier/tags til BeerSniffers øltyper."""
    cat_names = {c.get("name", "").lower() for c in categories}
    tag_names = {t.get("name", "").lower() for t in tags}
    all_names = cat_names | tag_names

    # Specifik mapping
    if "neipa" in all_names:
        return "India Pale Ale (IPA)"
    if "ipa" in all_names:
        return "India Pale Ale (IPA)"
    if "imperial stout" in all_names:
        return "Imperial Stout"
    if any("stout" in n for n in all_names):
        return "Stout"
    if any("porter" in n for n in all_names):
        return "Porter - Stout"
    if any("quadrupel" in n for n in all_names):
        return "Quadrupel"
    if any("sour" in n or "berliner" in n or "syrligt" in n or "vildtgæret" in n for n in all_names):
        return "Sour / Berliner Weisse"
    if any("saison" in n or "farmhouse" in n for n in all_names):
        return "Saison - Farmhouse Ale"
    if any("lager" in n for n in all_names):
        return "Lager"
    if any("pilsner" in n for n in all_names):
        return "Pilsner"
    if any("pale ale" in n for n in all_names):
        return "Pale Ale"
    if any("weissbier" in n or "wit" in n or "hvedeøl" in n for n in all_names):
        return "Hvedeøl - Witte"
    if any("brown ale" in n for n in all_names):
        return "Brown Ale"
    if any("red ale" in n or "amber" in n for n in all_names):
        return "Red Ale"
    if any("bock" in n for n in all_names):
        return "Bock"
    if any("dubbel" in n for n in all_names):
        return "Dubbel"
    if any("tripel" in n or "triple" in n for n in all_names):
        return "Tripel"
    if any("barley wine" in n or "barleywine" in n for n in all_names):
        return "Barley Wine"
    if any("gose" in n for n in all_names):
        return "Gose"
    if any("strong ale" in n or "dark ale" in n for n in all_names):
        return "Strong Ale"
    if any("blonde" in n or "blond" in n for n in all_names):
        return "Blonde Ale"
    if any("røgøl" in n or "rauch" in n for n in all_names):
        return "Røgøl"
    if any("lambic" in n for n in all_names):
        return "Lambic"
    if any("alkoholfri" in n for n in all_names):
        return "Alkoholfri"
    if any("mjød" in n or "mead" in n for n in all_names):
        return "Mjød"

    # Fallback: brug første ølkategori direkte
    for c in categories:
        name = c.get("name", "")
        if name.lower() not in SKIP_CATEGORIES:
            return name

    return ""


def scrape_ol2go():
    """Henter alle øl fra ØL2GO via WooCommerce Store API."""
    items = []
    page = 1

    print("🍺 Henter øl fra ØL2GO (WooCommerce)...")

    while True:
        url = f"{BASE_URL}?per_page=100&page={page}"
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                print(f"  ⚠️ Side {page}: HTTP {r.status_code}")
                break
            products = r.json()
        except Exception as e:
            print(f"  ❌ Fejl på side {page}: {e}")
            break

        if not products:
            break

        for p in products:
            name = unescape(p.get("name", ""))
            if not name:
                continue

            # Spring ikke-øl over
            if not p.get("is_in_stock"):
                continue

            name_lower = name.lower()
            if any(kw in name_lower for kw in SKIP_KEYWORDS):
                continue

            categories = p.get("categories", [])
            cat_slugs = {c.get("slug", "") for c in categories}
            cat_names_lower = {c.get("name", "").lower() for c in categories}

            # Spring over hvis KUN i en skip-kategori
            if cat_names_lower and cat_names_lower.issubset(SKIP_CATEGORIES):
                continue

            # Pris (minor units → kr)
            prices = p.get("prices", {})
            minor_unit = prices.get("currency_minor_unit", 2)
            divisor = 10 ** minor_unit

            try:
                price = int(prices.get("price", 0)) / divisor
            except (ValueError, TypeError):
                continue

            if price <= 0:
                continue

            old_price = None
            discount = None
            if p.get("on_sale"):
                try:
                    reg = int(prices.get("regular_price", 0)) / divisor
                    if reg > price:
                        old_price = reg
                        discount = round((reg - price) / reg * 100, 1)
                except (ValueError, TypeError):
                    pass

            # Produktdata
            slug = p.get("slug", "")
            product_url = p.get("permalink", f"https://ol2go.dk/vare/{slug}/")

            image = None
            images = p.get("images", [])
            if images:
                image = images[0].get("src")

            tags = p.get("tags", [])
            beer_type = _map_category(categories, tags)

            weight_g = p.get("weight")
            volume = _parse_volume(name, weight_g)

            desc = unescape(p.get("short_description", ""))
            abv = _parse_abv(name, desc)

            items.append({
                "name": name,
                "brewery": None,  # ØL2GO har ikke bryggeri som separat felt
                "type": beer_type,
                "abv": abv,
                "volume_cl": volume,
                "price": price,
                "old_price": old_price,
                "discount_pct": discount,
                "url": product_url,
                "image": image,
                "shop_name": "ØL2GO",
                "description": desc,
            })

        print(f"  📦 Side {page}: {len(products)} produkter")
        page += 1

    print(f"✅ {len(items)} øl hentet fra ØL2GO")
    return items


if __name__ == "__main__":
    beers = scrape_ol2go()
    for b in beers[:5]:
        print(f"  {b['name']} — {b['price']} kr — {b['type']} — {b['volume_cl']}cl — {b['abv']}%")