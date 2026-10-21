# app/scrapers/olleglad.py
import re
import requests
from app.utils.detect_type import detect_type
from app.utils.description import clean_description

SHOP_NAME = 'Ølleglad'
SHOP_URL = 'https://olleglad.dk'
SHOP_SHIPPING = {'price': 49, 'freeOver': 599, 'note': 'Levering med GLS'}

_FEED_URL = (
    'https://olleglad.dk/feed/beersniffer-nbak3wkdmme74ibqgyrd8n81.json'
)

_RE_VOLUME = re.compile(r'(?:Størrelse|Indhold)[:\s]+(\d+[.,]?\d*)\s*cl\b|(\d+[.,]?\d*)\s*cl\b', re.IGNORECASE)
_RE_ABV    = re.compile(r'(\d+[.,]?\d+|\d+)\s*%\s*(?:vol\.?|alkohol)?', re.IGNORECASE)
_RE_EMOJI  = re.compile(
    r'[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F900-\U0001F9FF]'
)


def _parse_volume(text: str) -> float | None:
    # Prioritér "Størrelse: XX cl" / "Indhold: XX cl" frem for første tilfældige cl-nævnelse
    for m in _RE_VOLUME.finditer(text):
        raw = m.group(1) or m.group(2)
        if not raw:
            continue
        try:
            val = float(raw.replace(',', '.'))
            if 5 <= val <= 3000:
                return val
        except ValueError:
            continue
    return None


def _parse_abv(text: str) -> float | None:
    for m in _RE_ABV.finditer(text):
        try:
            val = float(m.group(1).replace(',', '.'))
            if 0.5 <= val <= 25:
                return val
        except ValueError:
            pass
    return None


def _clean_brewery(brand: str) -> str:
    """Strip flag-emojis og lignende fra brand-feltet.
    Bemærk: brewery udtrækkes fra brand INDEN clean_description,
    så Blech.Brut ikke bliver til 'Blech. Brut' af sætningsdetektering.
    """
    cleaned = _RE_EMOJI.sub('', brand).strip()
    cleaned = re.sub(r'\s*\([A-Z]{2}\)\s*$', '', cleaned).strip()
    # Fjern mellemrum der ved en fejl er sat ind efter punktum i bryggerinavne
    # f.eks. "Blech. Brut" → "Blech.Brut"
    cleaned = re.sub(r'(?<=\w)\.\s+(?=\w)', '.', cleaned)
    return cleaned or brand


def scrape_olleglad() -> list[dict]:
    resp = requests.get(_FEED_URL, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for item in data:
        name = (item.get('name') or '').strip()
        if not name:
            continue

        price = item.get('price') or item.get('real_price')
        try:
            price = float(price)
        except (TypeError, ValueError):
            continue
        if price <= 5:
            continue

        old_price = item.get('real_price')
        try:
            old_price = float(old_price)
        except (TypeError, ValueError):
            old_price = None

        discount_pct = None
        if old_price and price < old_price:
            discount_pct = round((1 - price / old_price) * 100, 1)
        else:
            old_price = None  # ingen rabat → gem ikke

        desc_raw  = item.get('description_text') or ''
        volume_cl = _parse_volume(desc_raw)
        abv       = _parse_abv(desc_raw)
        brewery   = _clean_brewery(item.get('brand') or '')
        url       = item.get('url') or SHOP_URL
        image     = item.get('image') or None

        category  = (item.get('main_category') or '').strip()
        beer_type = detect_type(name) or detect_type(category) or None

        description = clean_description(desc_raw) if desc_raw else None

        results.append({
            'name':         name,
            'price':        price,
            'shop_name':    SHOP_NAME,
            'url':          url,
            'image':        image,
            'brewery':      brewery if brewery else None,
            'volume_cl':    volume_cl,
            'abv':          abv,
            'type':         beer_type,
            'description':  description,
            'old_price':    old_price,
            'discount_pct': discount_pct,
        })

    return results


if __name__ == '__main__':
    beers = scrape_olleglad()
    print(f'{len(beers)} øl hentet fra {SHOP_NAME}')
    for b in beers[:5]:
        print(b)
