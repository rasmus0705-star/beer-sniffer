import requests
import xml.etree.ElementTree as ET
import re
from app.utils.detect_type import detect_type

FEED_URL = "https://www.partner-ads.com/dk/feed_udlaes.php?partnerid=56605&bannerid=74625&feedid=1666"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}


# Mojibake-mønstre fra Beer Me's blandede UTF-8/ISO-8859-1 encoding
MOJIBAKE_FIXES = [
    ('Â·', '·'),       # middle dot
    ('Â\xa0', ' '),    # non-breaking space
    ('â€"', '–'),      # en-dash
    ('â€"', '—'),      # em-dash
    ('â€™', '\''),     # right single quotation
    ('â€˜', '\''),     # left single quotation
    ('â€œ', '"'),      # left double quotation
    ('â€\x9d', '"'),   # right double quotation
    ('Ã¦', 'æ'),
    ('Ã¸', 'ø'),
    ('Ã¥', 'å'),
    ('Ã†', 'Æ'),
    ('Ã˜', 'Ø'),
    ('Ã…', 'Å'),
    ('Ã©', 'é'),
    ('Ã¨', 'è'),
    ('Ãª', 'ê'),
    ('Ã¤', 'ä'),
    ('Ã¶', 'ö'),
    ('Ã¼', 'ü'),
]


def clean_mojibake(text):
    """Rens forvanskede tegn fra Beer Me's blandede encoding."""
    if not text:
        return text
    for bad, good in MOJIBAKE_FIXES:
        text = text.replace(bad, good)
    return text


def extract_brewery_from_name(name):
    """
    Beer Me-navne har konsistent format:
      "[Produktnavn] - [Stil] fra [Bryggeri]"
      "[Produktnavn] · [Stil] fra [Bryggeri]"
      "[Produktnavn] [Stil] fra [Bryggeri]"
    """
    if not name:
        return None

    # Primær: " fra X"
    fra_match = re.search(r"\bfra\s+(.+?)$", name, re.IGNORECASE)
    if fra_match:
        candidate = fra_match.group(1).strip()
        candidate = re.sub(r"\s*\(.*?\)\s*$", "", candidate).strip()
        if candidate and len(candidate.split()) <= 5 and not re.match(r"^\d+\s*(cl|ml|%)", candidate.lower()):
            return candidate

    # Fallback 1: " · " separator
    if " · " in name:
        parts = name.split(" · ")
        candidate = parts[-1].strip()
        if candidate and len(candidate.split()) <= 5 and not re.search(r"\d+\s*(cl|ml|%)", candidate.lower()):
            return candidate

    # Fallback 2: " - " separator
    if " - " in name:
        parts = name.split(" - ")
        if len(parts) == 2:
            candidate = parts[-1].strip()
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
        # Rens mojibake fra alle felter
        name = clean_mojibake(produkt.findtext('produktnavn') or '')
        category = clean_mojibake((produkt.findtext('kategorinavn') or '').upper())

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

        # Volume — tjek navnet for cl/ml/l
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
                volume = 33

        # ABV
        abv = None
        match = re.search(r'(\d+(?:[.,]\d+)?)\s*%', name)
        if match:
            abv = float(match.group(1).replace(',', '.'))

        # Bryggeri via " fra X" pattern
        brewery = extract_brewery_from_name(name)

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
    with_brewery = sum(1 for it in items if it.get("brewery"))
    print(f"Med bryggeri: {with_brewery}/{len(items)} ({100*with_brewery//len(items)}%)")
    print(f"\nFørste 5 items:")
    for it in items[:5]:
        print(f"  - {it['name']}")
        print(f"    → Brewery: {it.get('brewery')}")