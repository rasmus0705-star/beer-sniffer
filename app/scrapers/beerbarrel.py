"""
beerbarrel.py — Scraper til BeerBarrel (beerbarrel.dk) via WooCommerce Store API.

Flow:
  1. /wp-json/wc/store/v1/products?per_page=100&page=N  -> navn, pris, førpris, billede,
     attributter, kategorier, beskrivelse
  2. Bryggeri: attribut -> link til /bryggeri/<slug>/ i beskrivelsen -> produktside
  3. Mangler ABV/cl/bryggeri stadig: produktsidens "Fakta om øllen"-liste (cachet)

BeerBarrels produktnavne indeholder IKKE bryggeriet ("Winter Smooth"), så bryggeri-
udtrækket er vigtigt for matchningen.

Test:        python -m app.scrapers.beerbarrel
Rå API-dump: python -m app.scrapers.beerbarrel --dump
"""
import html
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

from app.utils.description import clean_description
from app.utils.detect_type import detect_type

SHOP_NAME = 'BeerBarrel'
SHOP_URL = 'https://www.beerbarrel.dk'
SHOP_SHIPPING = {'price': 60, 'freeOver': 599, 'note': 'Gratis til pakkeshop ved køb over 599 kr.'}

BASE = 'https://www.beerbarrel.dk'
API_URL = f'{BASE}/wp-json/wc/store/v1/products'
PER_PAGE = 100
SIDE_PAUSE = 0.3
SIDE_TIMEOUT = 12

_CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_cache_beerbarrel.json')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/128.0 Safari/537.36',
    'Accept': 'application/json, text/html;q=0.9, */*;q=0.8',
    'Accept-Language': 'da-DK,da;q=0.9,en;q=0.8',
    'Referer': f'{BASE}/shop/',
    'Origin': BASE,
}

SKIP_CATEGORIES = {'bundle', 'bundles', 'cider', 'gavekort', 'merchandise', 'glas', 'tilbehor'}
SKIP_KEYWORDS = ('bundle', 'gavekort', 'glas', 't-shirt', 'hoodie', 'oplukker')

_PCT_RE = re.compile(r'(?<![\d.,])(\d{1,2}(?:[.,]\d{1,2})?)\s*%')
_VOL_RE = re.compile(r'(?<![\d.,])(\d{1,4}(?:[.,]\d{1,2})?)\s*(cl|ml|l)\b\.?', re.I)
PAGE_HEADERS = {**HEADERS, 'Accept': 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.8'}
_BREW_LINK_RE = re.compile(r'<a[^>]+href="[^"]*/bryggeri/([^/"]+)/?"[^>]*>(.*?)</a>', re.I | re.S)


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
        print(f'  [BeerBarrel] kunne ikke gemme cache: {e}')


# ---------------------------------------------------------------- helpers
def _txt(s):
    s = re.sub(r'<[^>]+>', ' ', s or '')
    s = html.unescape(s).replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', s).strip()


def _num(s):
    try:
        return float(str(s).replace(',', '.'))
    except ValueError:
        return None


def _abv(s):
    if len(s or '') > 25:
        return None
    m = _PCT_RE.search(s or '')
    if m:
        v = _num(m.group(1))
        if v is not None and 0 <= v <= 20:
            return v
    return None


def _vol(s):
    if len(s or '') > 25:
        return None
    m = _VOL_RE.search(s or '')
    if not m:
        return None
    v = _num(m.group(1))
    unit = m.group(2).lower()
    if unit == 'ml':
        v = v / 10
    elif unit == 'l':
        v = v * 100
    return round(v, 1) if v and 5 <= v <= 300 else None


def _price(prices, key):
    raw = prices.get(key)
    if raw in (None, ''):
        return None
    minor = int(prices.get('currency_minor_unit', 2))
    try:
        return int(raw) / (10 ** minor)
    except ValueError:
        return None


def _from_attributes(attrs):
    """Map WooCommerce-attributter -> brewery/abv/volume_cl/style.
    Navne-baseret først, derefter værdi-baseret fallback (12% / 33 cl)."""
    out = {}
    loose = []
    for a in attrs or []:
        aname = _txt(a.get('name') or a.get('taxonomy') or '').lower()
        terms = [_txt(t.get('name')) for t in (a.get('terms') or []) if t.get('name')]
        if not terms:
            continue
        val = terms[0]
        if 'bryg' in aname or 'brewery' in aname or 'producent' in aname:
            out.setdefault('brewery', val)
        elif 'alkohol' in aname or 'abv' in aname or 'procent' in aname:
            v = _abv(val if '%' in val else val + '%')
            if v is not None:
                out.setdefault('abv', v)
        elif any(k in aname for k in ('indhold', 'volumen', 'størrelse', 'storrelse', 'flaske')):
            v = _vol(val if re.search(r'[a-z]', val, re.I) else val + ' cl')
            if v:
                out.setdefault('volume_cl', v)
        elif 'type' in aname or 'stil' in aname:
            out.setdefault('style', val)
        loose.extend(terms)
    for t in loose:
        if 'abv' not in out and _abv(t) is not None:
            out['abv'] = _abv(t)
        if 'volume_cl' not in out and _vol(t):
            out['volume_cl'] = _vol(t)
    return out


def _brewery_from_description(desc_html):
    m = _BREW_LINK_RE.search(desc_html or '')
    if m:
        name = _txt(m.group(2))
        return name or m.group(1).replace('-', ' ').title()
    return None


_NON_BREWERY_CATS = {
    'uncategorized', 'ukategoriseret', 'spot', 'spotvarer', 'nyheder', 'tilbud', 'bundle',
    'bundles', 'oltype', 'ipa', 'stout', 'sour', 'ale', 'lager', 'barley-wine', 'porter',
    'hvedeoel', 'kolsch', 'quadrupel', 'brett', 'alkoholfri-oel', 'cider',
}


def _brewery_from_categories(cats):
    for c in cats or []:
        slug = (c.get('slug') or '').lower()
        name = _txt(c.get('name'))
        if slug and slug not in _NON_BREWERY_CATS and name:
            return name
    return None


def _parse_fakta(page_html):
    """'Fakta om øllen': type, abv, IBU, smag, volumen, bryggeri, land (uden labels).
    Bryggeri = punktet lige efter volumen."""
    soup = BeautifulSoup(page_html, 'html.parser')
    out = {}
    anchor = soup.find(string=re.compile(r'Fakta om øllen', re.I))
    from_h1 = False
    lis = []
    if anchor:
        # Hvert punkt kan ligge i sin egen <ul> - saml alle <li> til næste h1/h2
        for el in anchor.find_all_next(['li', 'h1', 'h2']):
            if el.name in ('h1', 'h2'):
                break
            lis.append(el)
            if len(lis) >= 12:
                break
    if not lis:
        h1 = soup.find('h1')
        ul = h1.find_next('ul') if h1 else None
        lis = ul.find_all('li') if ul else []
        from_h1 = True  # h1-listen har ikke bryggeri (4. punkt er land)
    if not lis:
        return out
    items = [_txt(li.get_text(' ')) for li in lis]
    items = [i for i in items if i]
    if items and not _abv(items[0]) and not _vol(items[0]):
        out['style'] = items[0]
    for i, it in enumerate(items):
        if 'abv' not in out and _abv(it) is not None:
            out['abv'] = _abv(it)
        if 'volume_cl' not in out and _vol(it):
            out['volume_cl'] = _vol(it)
            if i + 1 < len(items):
                cand = items[i + 1]
                if not from_h1 and cand.lower() != 'ikke oplyst' and len(cand) <= 50:
                    out['brewery'] = cand
    return out


def _is_skip(p):
    cats = {(c.get('slug') or '').lower() for c in p.get('categories') or []}
    if cats & SKIP_CATEGORIES:
        return True
    n = _txt(p.get('name')).lower()
    return any(re.search(rf'\b{re.escape(k)}\b', n) for k in SKIP_KEYWORDS)


def _fetch_page(session, url, failed):
    why = '?'
    for attempt in range(3):
        try:
            r = session.get(url, headers=PAGE_HEADERS, timeout=25)
            if r.status_code == 200:
                det = _parse_fakta(r.text)
                if det:
                    return det
                failed.append((url, 'ingen fakta i HTML'))
                return None
            why = f'HTTP {r.status_code}'
        except requests.RequestException as e:
            why = type(e).__name__
        time.sleep(2 * (attempt + 1))
    failed.append((url, why))
    return None


# ---------------------------------------------------------------- api
def _fetch_api(session):
    products, page = [], 1
    while True:
        try:
            r = session.get(API_URL, params={'per_page': PER_PAGE, 'page': page},
                            headers=HEADERS, timeout=25)
        except requests.RequestException as e:
            print(f'  [BeerBarrel] API-fejl side {page}: {e}')
            break
        if r.status_code != 200:
            print(f'  [BeerBarrel] API svarede {r.status_code} på side {page}')
            break
        try:
            batch = r.json()
        except ValueError:
            print('  [BeerBarrel] API returnerede ikke JSON (bot-beskyttelse?)')
            break
        if not batch:
            break
        products.extend(batch)
        total_pages = int(r.headers.get('X-WP-TotalPages', page))
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.3)
    return products


# ---------------------------------------------------------------- main
def scrape_beerbarrel():
    session = requests.Session()
    products = _fetch_api(session)
    print(f'  [BeerBarrel] {len(products)} produkter fra API')

    cache = _cache_load()
    fetched = 0
    failed = []
    results = []
    for p in products:
        if not p.get('is_in_stock', True) or _is_skip(p):
            continue
        prices = p.get('prices') or {}
        price = _price(prices, 'price')
        if not price or price <= 5:
            continue
        regular = _price(prices, 'regular_price')
        url = p.get('permalink')
        name = _txt(p.get('name'))

        info = _from_attributes(p.get('attributes'))
        if 'brewery' not in info:
            b = _brewery_from_categories(p.get('categories'))
            if b:
                info['brewery'] = b
        if 'brewery' not in info:
            b = _brewery_from_description(p.get('description')) or \
                _brewery_from_description(p.get('short_description'))
            if b:
                info['brewery'] = b

        if url and not all(k in info for k in ('brewery', 'abv', 'volume_cl')):
            det = cache.get(url)
            if det is None:
                det = _fetch_page(session, url, failed)
                if det:
                    cache[url] = det
                    fetched += 1
                time.sleep(SIDE_PAUSE)
            for k, v in (det or {}).items():
                info.setdefault(k, v)

        images = p.get('images') or []
        item = {
            'name': name,
            'price': price,
            'shop_name': SHOP_NAME,
            'url': url,
            'brewery': info.get('brewery'),
            'volume_cl': info.get('volume_cl'),
            'abv': info.get('abv'),
            'type': detect_type(f"{name} {info.get('style') or ''}"),
            'image': images[0].get('src') if images else None,
            'description': clean_description(p.get('short_description') or p.get('description') or ''),
        }
        if regular and regular > price:
            item['old_price'] = regular
            item['discount_pct'] = round((1 - price / regular) * 100)
        results.append(item)

    if fetched:
        _cache_save(cache)
    print(f'  [BeerBarrel] {len(results)} øl ({fetched} produktsider hentet, {len(failed)} fejlede)')
    for u, why in failed[:10]:
        print(f'    FEJL {why}: {u}')
    return results


if __name__ == '__main__':
    if '--url' in sys.argv:
        u = sys.argv[sys.argv.index('--url') + 1]
        r = requests.get(u, headers=PAGE_HEADERS, timeout=25)
        print('Status:', r.status_code, '| bytes:', len(r.text),
              '| "Fakta om øllen" i HTML:', 'Fakta om øllen' in r.text)
        print(_parse_fakta(r.text))
        sys.exit()
    if '--dump' in sys.argv:
        r = requests.get(API_URL, params={'per_page': 3}, headers=HEADERS, timeout=25)
        print('Status:', r.status_code, '| TotalPages:', r.headers.get('X-WP-TotalPages'))
        for p in r.json():
            print('\n==', p.get('name'), p.get('permalink'))
            print('  prices    :', p.get('prices'))
            print('  categories:', [c.get('slug') for c in p.get('categories') or []])
            print('  attributes:', [(a.get('name'), [t.get('name') for t in a.get('terms') or []])
                                    for a in p.get('attributes') or []])
            print('  bryggeri-link i beskrivelse:', _brewery_from_description(p.get('description')))
        sys.exit()

    beers = scrape_beerbarrel()
    n = len(beers) or 1
    for k in ('brewery', 'abv', 'volume_cl', 'type', 'image'):
        c = sum(1 for b in beers if b.get(k))
        print(f'  {k:10} {c}/{len(beers)} ({100 * c // n}%)')
    for b in beers[:8]:
        print(f"  {b['price']:>7.2f}  {b.get('volume_cl') or '-':>5}cl  {b.get('abv') or '-':>4}%  "
              f"{(b.get('brewery') or '?')[:22]:22}  {b['name'][:60]}")
