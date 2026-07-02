import requests
import xml.etree.ElementTree as ET
import re
from app.utils.detect_type import detect_type
from app.utils.description import clean_description


# --- Brewery-fallback: udled bryggeri fra titel naar g:brand er tom ---
_BREWERY_SKIP_WORDS = {
    "oel", "øl", "oelpakke", "ølpakke", "pakke", "smagekasse",
    "smagessæt", "blandet", "mix", "gavekurv", "gave", "kasse",
}

def _brewery_from_title(title):
    """Returner sandsynligt bryggeri fra titel, ellers None.
    Tager teksten foer foerste ',' eller ' - '. Konservativt."""
    if not title:
        return None
    t = title.strip()
    low = t.lower()
    # spring pakker/blandinger over - de har ikke ET bryggeri
    if any(w in low for w in ["pakke", "smagekasse", "smagess", "blandet", "bland selv", "gavekurv"]):
        return None
    # find foerste separator: komma vinder over ' - ' hvis den kommer foerst
    cut = len(t)
    ci = t.find(",")
    if ci != -1:
        cut = min(cut, ci)
    di = t.find(" - ")
    if di != -1:
        cut = min(cut, di)
    if cut == len(t):
        return None  # ingen separator -> for usikkert
    cand = t[:cut].strip()
    # afvis for korte / generiske kandidater
    if len(cand) < 3:
        return None
    if cand.lower() in _BREWERY_SKIP_WORDS:
        return None
    # afvis hvis kandidaten ligner en stilart frem for et bryggeri (valgfrit, let)
    return cand

FEED_URL = "https://files.channable.com/KOFt2pJuP6mHNcln83Tm7Q==.xml"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# Google Shopping namespace
NS = {"g": "http://base.google.com/ns/1.0"}


def parse_price(price_str):
    """Parser '44.00 DKK' → 44.0"""
    if not price_str:
        return None
    match = re.search(r"(\d+[.,]?\d*)", price_str)
    if match:
        try:
            return float(match.group(1).replace(",", "."))
        except:
            return None
    return None


def parse_volume(measure_str, description):
    """
    Parser volume fra '500 ml', '33 cl' osv.
    Hvis ikke i unit_pricing_measure, prøv description.
    """
    if measure_str:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(ml|cl|l)", measure_str.lower())
        if m:
            val = float(m.group(1).replace(",", "."))
            unit = m.group(2)
            if unit == "l":
                val = val * 100
            elif unit == "ml":
                val = val / 10
            return val

    # Fallback: led i description efter volume
    if description:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(ml|cl|l)\b", description.lower())
        if m:
            val = float(m.group(1).replace(",", "."))
            unit = m.group(2)
            if unit == "l":
                val = val * 100
            elif unit == "ml":
                val = val / 10
            return val
    return None


def parse_abv(description):
    """
    Description har formatet 'alkoholprocent på 6,50' eller 'Alc. 9,5% vol.'
    """
    if not description:
        return None

    # Primær: "alkoholprocent på X"
    m = re.search(r"alkoholprocent\s+på\s+(\d+(?:[.,]\d+)?)", description, re.IGNORECASE)
    if m:
        return float(m.group(1).replace(",", "."))

    # Fallback: standard X% pattern
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*%", description)
    if m:
        val = float(m.group(1).replace(",", "."))
        # Sanity check — ABV er typisk 0-15%
        if 0 <= val <= 20:
            return val

    return None


def scrape_vildmedvin():
    items = []

    try:
        r = requests.get(FEED_URL, headers=HEADERS, timeout=30)
        r.raise_for_status()
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"❌ Vild med Vin fejl: {e}")
        return items

    # Channable feed bruger <channel><item>...</item></channel> struktur
    # eller bare <item> direkte under root
    items_list = root.findall(".//item")

    skip_keywords = [
        "glas", "krus", "opener", "trøje", "gave", "gavekort",
        "merchandise", "snack", "chokolade", "anker", "fadøl",
        "abonnement", "pant", "tilbehør"
    ]

    for item in items_list:
        # Tjek at det er øl — Vild med Vin har vin og spiritus også!
        custom_label_3 = item.findtext("g:custom_label_3", default="", namespaces=NS)
        product_type = item.findtext("g:product_type", default="", namespaces=NS)

        # Skal være kategoriseret som øl
        is_beer = (
            custom_label_3.strip().lower() == "øl"
            or "øl" in product_type.lower()
            or "specialøl" in product_type.lower()
        )
        if not is_beer:
            continue

        # Skal være på lager
        availability = item.findtext("g:availability", default="", namespaces=NS)
        if availability.lower() != "in_stock":
            continue

        title = item.findtext("title", default="").strip()
        if not title:
            continue

        # Filtrer mod skip-keywords
        if any(kw in title.lower() for kw in skip_keywords):
            continue

        # Pris (foretrækker sale_price hvis billigere end price)
        price = parse_price(item.findtext("g:price", default="", namespaces=NS))
        sale_price = parse_price(item.findtext("g:sale_price", default="", namespaces=NS))

        if sale_price is not None and (price is None or sale_price < price):
            old_price = price if price and price > sale_price else None
            actual_price = sale_price
        else:
            old_price = None
            actual_price = price

        if not actual_price or actual_price <= 5:
            continue

        discount = None
        if old_price and old_price > actual_price:
            discount = round((old_price - actual_price) / old_price * 100, 1)

        # URL og billede
        url = item.findtext("link", default="").strip()
        image = item.findtext("g:image_link", default="", namespaces=NS).strip()

        # Bryggeri — direkte fra g:brand
        brewery = item.findtext("g:brand", default="", namespaces=NS).strip() or None
        if brewery is None:
            brewery = _brewery_from_title(title)

        # Description til ABV og fallback volume
        description = item.findtext("description", default="")

        # Volume
        unit_measure = item.findtext("g:unit_pricing_measure", default="", namespaces=NS)
        volume = parse_volume(unit_measure, description)

        # Filtrer flasker over 75cl (fadlagrede, store flasker)
        if volume and volume > 75:
            continue

        # ABV
        abv = parse_abv(description)

        # Type — vi prøver fra description og titel
        beer_type = detect_type(title)
        if not beer_type and description:
            # Description har ofte "Øllen er en X fra Y"
            type_match = re.search(r"Øllen er en (\w+(?:\s+\w+)?)\s+fra", description)
            if type_match:
                beer_type = type_match.group(1).strip()

        item_dict = {
            "name": title,
            "price": actual_price,
            "old_price": old_price,
            "discount_pct": discount,
            "url": url,
            "shop_name": "Vild med Vin",
            "volume_cl": volume,
            "abv": abv,
            "image": image,
            "type": beer_type,
            "brewery": brewery,
            "category": "øl",
            "description": clean_description(description),
        }

        items.append(item_dict)

    print(f"📦 Vild med Vin: {len(items)} produkter hentet")
    return items


if __name__ == "__main__":
    items = scrape_vildmedvin()
    print(f"\n✅ Total: {len(items)} items")

    # Statistik
    with_brewery = sum(1 for it in items if it.get("brewery"))
    with_volume = sum(1 for it in items if it.get("volume_cl"))
    with_abv = sum(1 for it in items if it.get("abv"))
    with_image = sum(1 for it in items if it.get("image"))
    with_description = sum(1 for it in items if it.get("description"))

    if items:
        print(f"\n📊 Coverage:")
        print(f"  Bryggeri: {with_brewery}/{len(items)} ({100*with_brewery//len(items)}%)")
        print(f"  Volume:   {with_volume}/{len(items)} ({100*with_volume//len(items)}%)")
        print(f"  ABV:      {with_abv}/{len(items)} ({100*with_abv//len(items)}%)")
        print(f"  Billede:  {with_image}/{len(items)} ({100*with_image//len(items)}%)")
        print(f"  Beskrivelse: {with_description}/{len(items)} ({100*with_description//len(items)}%)")

        print(f"\nEksempler på beskrivelser:")
        shown = 0
        for it in items:
            if it.get("description") and shown < 3:
                print(f"\n  📖 {it['name'][:60]}")
                print(f"     {it['description'][:200]}")
                shown += 1

        print(f"\nFørste 5 items:")
        for it in items[:5]:
            print(f"\n  📦 {it['name']}")
            print(f"     Pris: {it['price']} kr (rabat: {it.get('discount_pct')}%)")
            print(f"     ABV: {it.get('abv')}%, Volume: {it.get('volume_cl')}cl")
            print(f"     Bryggeri: {it.get('brewery')}, Type: {it.get('type')}")