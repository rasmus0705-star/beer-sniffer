import requests
import xml.etree.ElementTree as ET
import re
from app.utils.detect_type import detect_type

FEED_URL = "https://www.partner-ads.com/dk/feed_udlaes.php?partnerid=56605&bannerid=74625&feedid=1666"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


def extract_brewery(name):
    """
    Beer Me-navne har formatet "Produktnavn · Bryggeri" eller "Produktnavn - Bryggeri".
    Sidste del efter separatoren er typisk bryggeriet.
    """
    if not name:
        return None
    for sep in [" · ", " - ", " – ", " | "]:
        if sep in name:
            parts = name.split(sep)
            # Bryggeri er typisk det SIDSTE element
            candidate = parts[-1].strip()
            # Skal være rimeligt kort (max 4 ord) og ikke kun tal/enheder
            if candidate and len(candidate.split()) <= 4 and not re.search(r"\d+\s*(cl|ml|%)", candidate.lower()):
                return candidate
    return None


def scrape_beerme():
    items = []

    skip_keywords = [
        "abonnement", "subscription", "club", "beer club",
        "månedskasse", "gavekort", "gaveæske", "gave sæt",
        "glas", "tilbehør", "bundle"
    ]

    skip_categories = [
        "BEER CLUB", "GAVEIDEER", "GAVER", "ØLGAVER",
        "INTERNE PRODUKTER", "BEER CLUB FRI FRAGT TEST",
        "GLAS", "FREDAGSBAR", "ØL (ARKIV)"
    ]

    try:
        r = requests.get(FEED_URL, headers=HEADERS, timeout=15)
        r.encoding = 'iso-8859-1'
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"❌ Beer Me fejl: {e}")
        return items

    for produkt in root.findall('produkt'):
        name = produkt.findtext('produktnavn') or ''
        category = (produkt.findtext('kategorinavn') or '').upper()
        manufacturer = produkt.findtext('producent') or ''

        if not name:
            continue

        if any(cat in category for cat in skip_categories):
            continue

        if any(kw in name.lower() for kw in skip_keywords):
            continue

        lager = produkt.findtext('lagerantal') or ''
        if lager.lower() != 'in stock':
            continue

        try:
            price = float(produkt.findtext('nypris') or 0)
            old_price_raw = float(produkt.findtext('glpris') or 0)
        except:
            continue

        if price <= 0:
            continue

        old_price = old_price_raw if old_price_raw != price else None

        discount = None
        if old_price and old_price > price:
            discount = round((old_price - price) / old_price * 100, 1)

        url = produkt.findtext('vareurl') or ''
        image = produkt.findtext('billedurl') or ''

        # Volume — først tjek navnet, derefter standard patterns
        volume = None
        name_lower = name.lower()
        vol_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(cl|ml|l)\b", name_lower)
        if vol_match:
            val = float(vol_match.group(1).replace(",", "."))
            unit = vol_match.group(2)
            if unit == "l":
                val = val * 100
            elif unit == "ml":
                val = val / 10
            if val <= 75:
                volume = val
        else:
            if '33cl' in name_lower or '33 cl' in name_lower:
                volume = 33
            elif '44cl' in name_lower or '44 cl' in name_lower:
                volume = 44
            elif '50cl' in name_lower or '50 cl' in name_lower:
                volume = 50
            elif 'dåse' in name_lower:
                volume = 33  # standard dåse

        # ABV
        abv = None
        match = re.search(r'(\d+(?:[.,]\d+)?)\s*%', name)
        if match:
            abv = float(match.group(1).replace(',', '.'))

        # Brewery — først producent-felt, ellers udled fra navnet
        brewery = manufacturer.strip() if manufacturer else None
        if not brewery:
            brewery = extract_brewery(name)

        is_smagekasse = any(kw in name.lower() for kw in [
            "smagekasse", "smagesæt", "smagskasse", "mix", "bundle", "pakke"
        ]) or bool(re.search(r'\d+\s*stk', name.lower())) or category == 'ØLPAKKER'

        item = {
            "name": name,
            "price": price,
            "old_price": old_price,
            "discount_pct": discount,
            "url": url,
            "shop_name": "Beer Me",
            "volume_cl": volume,
            "abv": abv,
            "image": image,
            "type": detect_type(name),
            "brewery": brewery,
            "category": "smagekasse" if is_smagekasse else "øl",
        }

        items.append(item)

    print(f"📦 Beer Me: {len(items)} produkter hentet")
    return items


if __name__ == "__main__":
    items = scrape_beerme()
    print(f"\n✅ Total: {len(items)} items")
    # Tjek hvor mange der har brewery
    with_brewery = sum(1 for it in items if it.get("brewery"))
    print(f"Med bryggeri: {with_brewery}/{len(items)}")
    if items:
        print(f"\nFørste 3 items:")
        for it in items[:3]:
            print(f"  - {it['name']}")
            print(f"    Brewery: {it.get('brewery')}, ABV: {it.get('abv')}, Vol: {it.get('volume_cl')}cl")