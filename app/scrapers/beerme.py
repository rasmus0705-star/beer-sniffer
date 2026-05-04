import requests
import xml.etree.ElementTree as ET
import re
from app.utils.detect_type import detect_type

FEED_URL = "https://www.partner-ads.com/dk/feed_udlaes.php?partnerid=56605&bannerid=74625&feedid=1666"

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
        r = requests.get(FEED_URL, timeout=15)
        r.encoding = 'iso-8859-1'
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"❌ Beer Me fejl: {e}")
        return items

    for produkt in root.findall('produkt'):
        name = produkt.findtext('produktnavn') or ''
        category = (produkt.findtext('kategorinavn') or '').upper()

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

        volume = None
        name_lower = name.lower()
        if '33cl' in name_lower or '33 cl' in name_lower:
            volume = 33
        elif '44cl' in name_lower or '44 cl' in name_lower:
            volume = 44
        elif '50cl' in name_lower or '50 cl' in name_lower:
            volume = 50

        abv = None
        match = re.search(r'(\d+[.,]\d+)%', name)
        if match:
            abv = float(match.group(1).replace(',', '.'))

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
            "brewery": None,
            "category": "smagekasse" if is_smagekasse else "øl",
        }

        items.append(item)

    print(f"📦 Beer Me: {len(items)} produkter hentet")
    return items