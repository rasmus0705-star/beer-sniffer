import requests
import re
import html
import time
from app.utils.detect_type import detect_type


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
}

# Hent volumen/ABV fra produktsiden — kun når de mangler i json.
# Format på Øltankens sider: "8 % Dåse 47.3 cl. - USA" / "Flaske 37.5 cl."
SIDE_PAUSE = 0.5     # sekunder mellem produktside-kald (høflig mod serveren)
SIDE_TIMEOUT = 12

# Produktsider hentes som HTML, ikke JSON. (Accept: application/json giver en
# anden/reduceret side uden volumen-teksten "Flaske 37.5 cl".)
SIDE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
}


def _parse_abv(text):
    """Find ABV i tekst. Flere formater: '7.2 %', 'ABV: 7%', 'på 11% ABV'."""
    if not text:
        return None
    t = re.sub(r'<[^>]+>', ' ', text)
    t = re.sub(r'\s+', ' ', html.unescape(t))
    for pat in [
        r'abv\s*(?:p[\u00e5a]\s*|[:\s])\s*(\d+(?:[.,]\d+)?)\s*%',  # 'ABV: 7%'
        r'p[\u00e5a]\s*(\d+(?:[.,]\d+)?)\s*%\s*abv',               # 'på 11% ABV'
        r'-\s*(\d+(?:[.,]\d+)?)\s*%',                          # '- 7.2 %'
        r'(\d+(?:[.,]\d+)?)\s*%',                              # fallback
    ]:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            try:
                val = float(m.group(1).replace(',', '.'))
                if 0 < val <= 25:   # rimelig ABV-grænse
                    return val
            except ValueError:
                pass
    return None


def _fetch_from_page(url):
    """Hent (volume_cl, abv) fra en produktside. Hver kan være None."""
    try:
        r = requests.get(url, headers=SIDE_HEADERS, timeout=SIDE_TIMEOUT)
        if r.status_code != 200:
            return None, None
    except Exception:
        return None, None
    return _parse_volume(r.text), _parse_abv(r.text)


def _parse_volume(text):
    """Returner cl som float, eller None. Renser HTML først."""
    if not text:
        return None
    clean = re.sub(r'<[^>]+>', ' ', text)
    clean = html.unescape(clean).lower()
    m = re.search(r'(?:flaske|d[\u00e5a]se|str[\u00f8o]rrelse)\s*[:\s]*(\d+(?:[.,]\d+)?)\s*(cl|ml|l)\b', clean)
    if not m:
        m = re.search(r'(\d+(?:[.,]\d+)?)\s*(cl|ml|l)\b', clean)
    if m:
        val = float(m.group(1).replace(',', '.'))
        unit = m.group(2)
        if unit == 'l':
            val *= 100
        elif unit == 'ml':
            val /= 10
        if val <= 75:
            return val
    for pat, vol in [('33cl', 33), ('44cl', 44), ('50cl', 50)]:
        if pat in clean:
            return vol
    return None


def scrape_oeltanken():
    items = []
    page = 1

    skip_keywords = [
        "glas", "glass", "krus", "opener", "trøje", "t-shirt",
        "cap", "hat", "gave", "gavekort", "merchandise", "sodavand",
        "juice", "spiritus", "whisky", "gin", "rom", "vin", "wine",
        "snack", "chips", "nødder", "tilbehør", "renser", "brush",
        "børste", "tap", "pumpe", "slange", "pant", "ølglas",
        "chokolade", "chocolate", "fustage", "fadøl", "keg", "anker",
        # Læskedrik / sodavand (matcher hele ord, ikke dele af ølnavne)
        "brus", "danskvand", "citronvand", "kombucha",
        # Ikke-øl: abonnement, info-sider, firmaaftaler
        "abonnoment", "abonnement", "firmaaftale", "firma-aftale",
        "info om muligheder", "fredagsbar",
    ]

    # Ebeltoft Gaardbryggeri laver både øl OG sodavand. Disse er sodavand:
    skip_exact = [
        "ebeltoft gaardbryggeri - ebeltoft cola",
        "ebeltoft gaardbryggeri - ingefær & citron",
        "ebeltoft gaardbryggeri - siciliansk appelsin",
        "ebeltoft gaardbryggeri - siciliansk citron",
    ]

    while True:
        url = f"https://oltanken.dk/products.json?limit=250&page={page}"

        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            data = response.json()
        except Exception as e:
            print(f"❌ Øltanken fejl på side {page}: {e}")
            break

        products = data.get("products", [])
        if not products:
            break

        for product in products:
            name = product.get("title")
            if not name:
                continue

            if any(kw in name.lower() for kw in skip_keywords):
                continue

            if name.lower().strip() in skip_exact:
                continue

            variants = product.get("variants", [])
            if not variants:
                continue

            variant = variants[0]
            if not variant.get("available"):
                continue

            try:
                price = float(variant.get("price"))
            except:
                continue

            old_price = variant.get("compare_at_price")
            if old_price:
                try:
                    old_price = float(old_price)
                except:
                    old_price = None

            discount = None
            if old_price and old_price > price:
                discount = round(((old_price - price) / old_price) * 100, 1)

            handle = product.get("handle")
            product_url = f"https://oltanken.dk/products/{handle}"

            images = product.get("images", [])
            image = images[0].get("src") if images else None

            # Volumen: søg i navn → body_html → tags → variant-titler
            body_html = product.get("body_html", "")
            tags = product.get("tags", [])

            # Er det en bundle/smagekasse? (skal IKKE have udledt volumen)
            name_lower = name.lower()
            is_smagekasse = (
                any(kw in name_lower for kw in [
                    "smagekasse", "smagesæt", "smagskasse", "smagspakke",
                    "smagsepakke", "smagkasse", "bundle", "bland selv",
                    "blandet", "vælg", "sæt", "mix", "spar op til", "pakke",
                ])
                or bool(re.search(r'\d+\s*stk', name_lower))
                or "+ glas" in name_lower
                # Flere årgange/versioner solgt samlet, fx 'V17 + V18', '22, 23 & 24'
                or bool(re.search(r'v\d+\s*\+\s*v\d+', name_lower))
                or bool(re.search(r'\d+,\s*\d+.*&\s*\d+', name_lower))
            )

            volume = (
                _parse_volume(name)
                or _parse_volume(body_html)
                or next((_parse_volume(t) for t in tags if _parse_volume(t)), None)
                or next((_parse_volume(v.get("title", "")) for v in variants if _parse_volume(v.get("title", ""))), None)
            )

            # ABV: søg i navn → body_html → tags
            abv = _parse_abv(name) or _parse_abv(body_html) or _parse_abv(' '.join(tags))

            # SIDEHENTNING — kun for enkeltøl der STADIG mangler volumen/abv.
            # Henter de faktiske værdier fra produktsiden (ingen gæt).
            # Gated, så vi kun besøger sider hvor noget mangler.
            if not is_smagekasse and (volume is None or abv is None):
                p_vol, p_abv = _fetch_from_page(product_url)
                if volume is None and p_vol is not None:
                    volume = p_vol
                if abv is None and p_abv is not None:
                    abv = p_abv
                time.sleep(SIDE_PAUSE)

            # Bryggeri: split på ' - ' eller brug vendor
            brewery = None
            if ' - ' in name:
                brewery = name.split(' - ')[0].strip()
            if not brewery:
                brewery = product.get("vendor") or None

            # Untappd
            untappd_url = None
            untappd_id = None
            untappd_match = re.search(
                r'https://untappd\.com/b/[^/]+/(\d+)', body_html
            )
            if untappd_match:
                untappd_id = untappd_match.group(1)
                untappd_url_match = re.search(
                    r'https://untappd\.com/b/[^"]+', body_html
                )
                if untappd_url_match:
                    untappd_url = untappd_url_match.group(0)

            # Type
            beer_type = detect_type(name) or detect_type(' '.join(tags))

            item = {
                "external_id": product.get("id"),
                "name": name,
                "price": price,
                "old_price": old_price,
                "discount_pct": discount,
                "url": product_url,
                "shop_name": "Øltanken",
                "volume_cl": volume,
                "grams": variant.get("grams"),
                "abv": abv,
                "image": image,
                "type": beer_type,
                "brewery": brewery,
                "category": "smagekasse" if is_smagekasse else "øl",
                "sku": variant.get("sku"),
                "available": variant.get("available"),
                "untappd_url": untappd_url,
                "untappd_id": untappd_id,
                "tags": tags,
            }

            items.append(item)

        print(f"📦 Øltanken side {page}: {len(products)} produkter hentet")
        page += 1

    return items


if __name__ == "__main__":
    items = scrape_oeltanken()
    print(f"\n✅ Total: {len(items)} items")
    with_brewery = sum(1 for it in items if it.get("brewery"))
    with_volume = sum(1 for it in items if it.get("volume_cl"))
    print(f"Med bryggeri: {with_brewery}/{len(items)}")
    print(f"Med volumen:  {with_volume}/{len(items)}")
    if items:
        print(f"\nFørste item:")
        for k, v in items[0].items():
            print(f"  {k}: {v}")