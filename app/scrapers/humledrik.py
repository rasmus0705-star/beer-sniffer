"""
humledrik.py — Scraper til Humledrik (humledrik.dk), Shoporama-webshop.

Flow:
  1. Kategorisiden /alle-vores-oel?p=0..N  -> navn, bryggeri, pris, førpris, billede, url
  2. Produktsiden (cachet)                 -> Alkohol %, Indhold cl, Øltype, Bryggeri, beskrivelse

Shoporama har intet offentligt JSON-API, så det er HTML. Produktsider caches i
_cache_humledrik.json, så kun nye varer hentes efter første kørsel.

Test:  python -m app.scrapers.humledrik
"""
import html
import json
import os
import re
import time

import requests
from bs4 import BeautifulSoup

from app.utils.description import clean_description
from app.utils.detect_type import detect_type

SHOP_NAME = 'Humledrik'
SHOP_URL = 'https://humledrik.dk'
SHOP_SHIPPING = {'price': 59, 'freeOver': 699, 'note': 'PostNord. Gratis levering på Fyn ved køb over 299 kr.'}

LIST_URL = 'https://humledrik.dk/alle-vores-oel'
MAX_PAGES = 40
LIST_PAUSE = 0.4
SIDE_PAUSE = 0.2
SIDE_TIMEOUT = 12

_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_cache_humledrik.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/128.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'da-DK,da;q=0.9,en;q=0.8',
}

# Ikke-øl der kan dukke op i kategorien
SKIP_KEYWORDS = ('gavekort', 'ølmenu', 'oelmenu', 'ølsmagning', 'bed and beer',
                 'glas', 'ølglas', 'gaveæske', 't-shirt', 'kasket', 'oplukker')

_PRICE_RE = re.compile(r'(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d{2})?)\s*kr', re.I)
_ABV_RE = re.compile(r'Alkohol\s*:?\s*(\d{1,2}(?:[.,]\d{1,2})?)\s*%', re.I)
_VOL_RE = re.compile(r'Indhold\s*:?\s*(\d{1,4}(?:[.,]\d{1,2})?)\s*(cl|ml|l)\b', re.I)
_TYPE_RE = re.compile(r'Øltype\s*:?\s*\n?\s*([^\n]{2,60})')
_BREW_RE = re.compile(r'(?m)^[ \t]*Bryggeri[ \t]*:?[ \t]*\n?[ \t]*([^\n]{2,60})')
_NAME_ABV_RE = re.compile(r'(?<![\d.,])(\d{1,2}(?:[.,]\d{1,2})?)\s*%')
_NAME_VOL_RE = re.compile(r'(\d{2,3}(?:[.,]\d)?)\s*cl\b', re.I)


# ---------------------------------------------------------------- cache
def _cache_load():
    try:
        with open(_CACHE_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _cache_save(cache):
    try:
        tmp = _CACHE_PATH + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=0)
        os.replace(tmp, _CACHE_PATH)
    except OSError as e:
        print(f'  [Humledrik] kunne ikke gemme cache: {e}')


# ---------------------------------------------------------------- helpers
def _txt(s):
    s = html.unescape(s or '').replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', s).strip()


def _num(s):
    """'1.234,50' / '59.00' / '59,00' -> float"""
    s = s.replace(' ', '')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    elif re.fullmatch(r'\d{1,3}\.\d{3}', s):
        s = s.replace('.', '')
    try:
        return float(s)
    except ValueError:
        return None


def _to_cl(value, unit):
    v = _num(value)
    if v is None:
        return None
    unit = unit.lower()
    if unit == 'ml':
        v = v / 10
    elif unit == 'l':
        v = v * 100
    return round(v, 1) if 5 <= v <= 300 else None


def _strip_brewery_suffix(name, brewery):
    """'Echo 2026 - Imperial Porter - Nepo Brewing' -> 'Echo 2026 - Imperial Porter'"""
    if not brewery or ' - ' not in name:
        return name
    parts = [p.strip() for p in name.split(' - ')]
    last = parts[-1].lower()
    b = brewery.lower()
    b_first = b.split()[0] if b.split() else b
    l_first = last.split()[0] if last.split() else last
    if last and (last in b or b in last or l_first == b_first):
        return ' - '.join(parts[:-1])
    return name


def _is_skip(name):
    n = name.lower()
    return any(re.search(rf'\b{re.escape(k)}\b', n) for k in SKIP_KEYWORDS)


# ---------------------------------------------------------------- liste
def _parse_card(li):
    h3 = li.find(['h3', 'h2'])
    a = h3.find('a', href=True) if h3 else None
    if not a:
        return None
    name = _txt(a.get_text(' '))
    url = a['href']
    if url.startswith('/'):
        url = SHOP_URL + url
    if not name or 'humledrik.dk' not in url:
        return None

    card_text = li.get_text('\n')
    if re.search(r'\budsolgt\b|ikke på lager', card_text, re.I):
        return None

    # Pris: gennemstreget = førpris
    old_price = None
    struck = li.find(['del', 's', 'strike'])
    if struck:
        m = _PRICE_RE.search(struck.get_text(' '))
        if m:
            old_price = _num(m.group(1))
    prices = [p for p in (_num(m.group(1)) for m in _PRICE_RE.finditer(card_text)) if p]
    if not prices:
        return None
    if old_price:
        rest = [p for p in prices if abs(p - old_price) > 0.001]
        price = min(rest) if rest else None
    else:
        price = prices[0]
    if not price:
        return None
    if old_price and old_price <= price:
        old_price = None

    # Bryggeri: sidste korte tekstlinje før produktnavnet
    brewery = None
    lines = [_txt(l) for l in card_text.split('\n')]
    lines = [l for l in lines if l]
    idx = next((i for i, l in enumerate(lines) if len(l) > 3 and name.startswith(l)), None)
    if idx is not None:
        for cand in reversed(lines[:idx]):
            if cand != name and len(cand) <= 50 and not _PRICE_RE.search(cand):
                brewery = cand
                break

    img = li.find('img')
    image = None
    if img:
        image = img.get('data-src') or img.get('src') or None
        if image and image.startswith('/'):
            image = SHOP_URL + image

    return {'name': name, 'url': url, 'price': price, 'old_price': old_price,
            'brewery': brewery, 'image': image}


def _fetch_list(session):
    items, seen = [], set()
    for p in range(MAX_PAGES):
        url = LIST_URL if p == 0 else f'{LIST_URL}?p={p}'
        try:
            r = session.get(url, headers=HEADERS, timeout=20)
            r.raise_for_status()
        except requests.RequestException as e:
            print(f'  [Humledrik] fejl på side {p + 1}: {e}')
            break
        soup = BeautifulSoup(r.text, 'html.parser')
        new = 0
        for li in soup.find_all('li'):
            if not li.find(['h3', 'h2']) or li.find('li'):
                continue  # kun "blade"-li'er med overskrift
            card = _parse_card(li)
            if card and card['url'] not in seen:
                seen.add(card['url'])
                items.append(card)
                new += 1
        if new == 0:
            break
        time.sleep(LIST_PAUSE)
    return items


# ---------------------------------------------------------------- produktside
def _parse_product_page(page_html):
    soup = BeautifulSoup(page_html, 'html.parser')
    for tag in soup(['head', 'title', 'script', 'style', 'nav', 'header', 'footer']):
        tag.decompose()
    text = soup.get_text('\n')
    text = re.sub(r'[ \t\xa0]+', ' ', text)

    out = {}
    m = _ABV_RE.search(text)
    if m:
        abv = _num(m.group(1))
        if abv is not None and 0 <= abv <= 20:
            out['abv'] = abv
    m = _VOL_RE.search(text)
    if m:
        vol = _to_cl(m.group(1), m.group(2))
        if vol:
            out['volume_cl'] = vol
    m = _TYPE_RE.search(text)
    if m:
        out['style'] = _txt(m.group(1))
    m = _BREW_RE.search(text)
    if m:
        out['brewery'] = _txt(m.group(1))

    og = BeautifulSoup(page_html, 'html.parser').find('meta', attrs={'property': 'og:description'})
    if og and og.get('content'):
        out['description'] = clean_description(html.unescape(og['content']))
    return out


def _fetch_details(session, url):
    try:
        r = session.get(url, headers=HEADERS, timeout=SIDE_TIMEOUT)
        r.raise_for_status()
    except requests.RequestException:
        return None
    return _parse_product_page(r.text)


# ---------------------------------------------------------------- main
def scrape_humledrik():
    session = requests.Session()
    cards = _fetch_list(session)
    print(f'  [Humledrik] {len(cards)} varer på listen')

    cache = _cache_load()
    fetched = 0
    results = []
    for c in cards:
        if _is_skip(c['name']):
            continue

        det = cache.get(c['url'])
        if det is None or 'volume_cl' not in det:
            new = _fetch_details(session, c['url'])
            if new is not None:
                det = new
                cache[c['url']] = new
                fetched += 1
                if fetched % 50 == 0:
                    _cache_save(cache)
                time.sleep(SIDE_PAUSE)
        det = det or {}

        brewery = c['brewery'] or det.get('brewery')
        name = _strip_brewery_suffix(c['name'], brewery)

        vol = det.get('volume_cl')
        if not vol:
            m = _NAME_VOL_RE.search(c['name'])
            if m:
                vol = _to_cl(m.group(1), 'cl')

        abv = det.get('abv')
        if abv is None:
            m = _NAME_ABV_RE.search(c['name'])
            if m:
                abv = _num(m.group(1))

        price = c['price']
        old_price = c['old_price']
        item = {
            'name': name,
            'price': price,
            'shop_name': SHOP_NAME,
            'url': c['url'],
            'brewery': brewery,
            'volume_cl': vol,
            'abv': abv,
            'type': detect_type(f"{c['name']} {det.get('style') or ''}"),
            'image': c['image'],
            'description': det.get('description'),
        }
        if old_price:
            item['old_price'] = old_price
            item['discount_pct'] = round((1 - price / old_price) * 100)
        if item['price'] > 5:
            results.append(item)

    if fetched:
        _cache_save(cache)
    print(f'  [Humledrik] {len(results)} øl ({fetched} produktsider hentet, resten fra cache)')
    return results


if __name__ == '__main__':
    beers = scrape_humledrik()
    n = len(beers) or 1
    for k in ('brewery', 'abv', 'volume_cl', 'type', 'image'):
        print(f'  {k:10} {sum(1 for b in beers if b.get(k))}/{len(beers)} '
              f'({100 * sum(1 for b in beers if b.get(k)) // n}%)')
    for b in beers[:8]:
        print(f"  {b['price']:>7.2f}  {b.get('volume_cl') or '-':>5}cl  {b.get('abv') or '-':>4}%  "
              f"{(b.get('brewery') or '?')[:22]:22}  {b['name'][:60]}")
