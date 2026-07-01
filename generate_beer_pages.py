"""
generate_beer_pages.py — Genererer statiske /ol/{slug}/index.html-sider,
én pr. øl, ud fra data.json.

SIKKERHED:
- Som standard genereres kun de første 10 øl (til test) — se dem først!
- Brug --all for at generere ALLE øl i data.json
- Brug --limit N for et andet antal test-sider
- Skriver KUN under ol/-mappen, rører intet andet i dit repo

Kør fra roden af dit projekt (samme sted som data.json):
    python generate_beer_pages.py              # laver 10 test-sider
    python generate_beer_pages.py --limit 25    # laver 25 test-sider
    python generate_beer_pages.py --all         # laver ALLE sider
"""

import json
import os
import sys
from datetime import datetime
from html import escape
from app.utils.slugify import clean_name

SITE_URL = "https://www.beersniffer.dk"
OUTPUT_DIR = "ol"


def load_data():
    with open("data.json", encoding="utf-8") as f:
        return json.load(f)


def format_price(p):
    return f"{p:.2f}".replace(".", ",")


def render_price_row(price, is_cheapest):
    shop = escape(price.get("shop_name", ""))
    amount = format_price(price.get("price", 0))
    old = price.get("old_price")
    discount = price.get("discount_pct") or 0
    url = escape(price.get("url", "") or "#")

    old_html = ""
    if old:
        old_html = f'<span class="old-price">{format_price(old)} kr</span>'

    discount_html = ""
    if discount:
        discount_html = f'<span class="discount-badge">−{discount:.0f}%</span>'

    cheapest_class = " cheapest" if is_cheapest else ""

    return f"""
    <div class="price-row{cheapest_class}">
        <div class="price-row-shop">{shop}{discount_html}</div>
        <div class="price-row-main">
            <div class="price-row-amounts">
                <span class="price-amount">{amount} kr</span>
                {old_html}
            </div>
            <a class="buy-btn" href="{url}" target="_blank" rel="noopener nofollow sponsored">Køb →</a>
        </div>
    </div>"""


def render_page(beer, updated_at):
    raw_name = beer.get("name", "")
    display_name = clean_name(raw_name)
    name = escape(display_name)
    brewery = escape(beer.get("brewery") or "")
    beer_type = escape(beer.get("type") or "")
    abv = beer.get("abv")
    volume = beer.get("volume_cl")
    image = beer.get("image") or ""
    slug = beer["slug"]
    prices = sorted(beer.get("prices", []), key=lambda p: p.get("price", 0))
    min_price = beer.get("min_price") or (prices[0]["price"] if prices else 0)
    max_discount = beer.get("max_discount_pct") or 0
    shop_count = len(prices)

    page_title = f"{name} – {format_price(min_price)} kr | BeerSniffer"
    meta_desc_parts = [name]
    if brewery:
        meta_desc_parts.append(f"fra {brewery}")
    meta_desc_parts.append(
        f"– sammenlign priser hos {shop_count} butik{'ker' if shop_count != 1 else ''}. "
        f"Billigste pris: {format_price(min_price)} kr."
    )
    meta_description = escape(" ".join(meta_desc_parts))

    canonical = f"{SITE_URL}/ol/{slug}/"

    meta_bits = []
    if beer_type:
        meta_bits.append(beer_type)
    if volume:
        meta_bits.append(f"{volume:.0f} cl")
    if abv is not None:
        meta_bits.append(f"{abv}% ABV")
    meta_line = " · ".join(meta_bits)

    price_rows_html = "".join(
        render_price_row(p, i == 0) for i, p in enumerate(prices)
    )

    untappd_query_name = display_name
    from urllib.parse import quote
    untappd_query = quote(untappd_query_name)

    schema = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": display_name,
        "image": image or None,
        "description": " ".join(meta_desc_parts),
        "brand": {"@type": "Brand", "name": beer.get("brewery") or "BeerSniffer"},
        "offers": {
            "@type": "AggregateOffer",
            "lowPrice": min_price,
            "priceCurrency": "DKK",
            "offerCount": shop_count,
            "offers": [
                {
                    "@type": "Offer",
                    "price": p.get("price"),
                    "priceCurrency": "DKK",
                    "url": p.get("url"),
                    "seller": {"@type": "Organization", "name": p.get("shop_name")},
                    "availability": "https://schema.org/InStock",
                }
                for p in prices
            ],
        },
    }
    schema_json = json.dumps(schema, ensure_ascii=False)

    image_html = (
        f'<img class="beer-image" src="{escape(image)}" alt="{name}" loading="eager">'
        if image else '<div class="beer-image-placeholder">🍺</div>'
    )

    return f"""<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(page_title)}</title>
<meta name="description" content="{meta_description}">
<link rel="canonical" href="{canonical}">
<meta property="og:title" content="{escape(page_title)}">
<meta property="og:description" content="{meta_description}">
<meta property="og:type" content="product">
<meta property="og:url" content="{canonical}">
{f'<meta property="og:image" content="{escape(image)}">' if image else ''}
<script type="application/ld+json">{schema_json}</script>
<style>
:root {{
    --bg: #0a0805; --surface: #141009; --surface2: #1e1810;
    --gold: #c8920e; --gold-light: #f0b832; --amber: #d4620a;
    --text: #f0e6d0; --text-muted: #7a6e5a; --border: #28200e;
    --border-light: #3a3020; --discount: #3dba6f;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--text); font-family: 'DM Sans', sans-serif; min-height: 100vh; }}
.wrap {{ max-width: 720px; margin: 0 auto; padding: 1.5rem; }}
.back-link {{ display: inline-block; color: var(--gold); text-decoration: none; font-size: 0.85rem; margin-bottom: 1.2rem; }}
.back-link:hover {{ color: var(--gold-light); }}
.beer-header {{ display: flex; gap: 1.2rem; margin-bottom: 1.5rem; }}
.beer-image, .beer-image-placeholder {{
    width: 140px; height: 140px; object-fit: contain; background: var(--surface2);
    border-radius: 12px; padding: 0.8rem; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center; font-size: 3rem;
}}
.beer-info h1 {{ font-size: 1.3rem; line-height: 1.35; margin-bottom: 0.4rem; }}
.beer-meta {{ font-size: 0.82rem; color: var(--text-muted); margin-bottom: 0.6rem; }}
.beer-brewery {{ font-size: 0.85rem; color: var(--gold-light); }}
.price-rows {{ display: flex; flex-direction: column; gap: 0.6rem; margin: 1.5rem 0; }}
.price-row {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.8rem 1rem; }}
.price-row.cheapest {{ border: 2px solid var(--gold); background: linear-gradient(135deg, rgba(200,146,14,0.1), rgba(212,98,10,0.04)); }}
.price-row-shop {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem; }}
.price-row-main {{ display: flex; justify-content: space-between; align-items: center; }}
.price-amount {{ font-size: 1.3rem; font-weight: 700; color: var(--gold-light); }}
.old-price {{ font-size: 0.8rem; color: #c0a878; text-decoration: line-through; margin-left: 0.5rem; }}
.discount-badge {{ background: var(--discount); color: #000; font-size: 0.65rem; font-weight: 800; padding: 0.1rem 0.4rem; border-radius: 4px; }}
.buy-btn {{ background: linear-gradient(135deg, #ffd54a, #ffb300); color: #000; font-weight: 800; padding: 0.5rem 1rem; border-radius: 7px; text-decoration: none; font-size: 0.8rem; }}
.disclaimer {{ font-size: 0.72rem; color: var(--text-muted); margin-top: 2rem; line-height: 1.6; border-top: 1px solid var(--border); padding-top: 1rem; }}
</style>
</head>
<body>
<div class="wrap">
    <a class="back-link" href="{SITE_URL}/">← Alle øltilbud</a>
    <div class="beer-header">
        {image_html}
        <div class="beer-info">
            <h1>{name}</h1>
            {f'<div class="beer-brewery">{brewery}</div>' if brewery else ''}
            <div class="beer-meta">{meta_line}</div>
        </div>
    </div>

    <div class="price-rows">
        {price_rows_html}
    </div>

    <p style="font-size:0.8rem;color:var(--text-muted)">
        Se også <a href="https://untappd.com/search?q={untappd_query}" target="_blank" rel="noopener" style="color:var(--gold)">{name} på Untappd</a>
    </p>

    <div class="disclaimer">
        📢 Affiliate disclosure: BeerSniffer kan modtage provision når du køber via vores links.
        Priser opdateret {updated_at}. Tjek altid den endelige pris hos forhandleren før køb.
    </div>
</div>
</body>
</html>"""


def main():
    all_mode = "--all" in sys.argv
    limit = 10
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        limit = int(sys.argv[idx + 1])

    data = load_data()
    beers = [b for b in data.get("beers", []) if b.get("slug")]
    updated_at = data.get("updated_at", "")
    try:
        d = datetime.fromisoformat(updated_at)
        updated_at_display = d.strftime("%d.%m.%Y")
    except Exception:
        updated_at_display = updated_at

    skipped_no_slug = len(data.get("beers", [])) - len(beers)
    if skipped_no_slug:
        print(f"⚠️ {skipped_no_slug} øl har ingen slug endnu og springes over.")

    if not all_mode:
        beers = beers[:limit]
        print(f"TEST-TILSTAND: genererer kun {len(beers)} sider (brug --all for alle {len(data.get('beers', []))}).")
    else:
        print(f"Genererer {len(beers)} sider...")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    written = []
    for beer in beers:
        slug = beer["slug"]
        page_dir = os.path.join(OUTPUT_DIR, slug)
        os.makedirs(page_dir, exist_ok=True)
        html = render_page(beer, updated_at_display)
        path = os.path.join(page_dir, "index.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        written.append(path)

    print(f"\n✅ Skrev {len(written)} sider til {OUTPUT_DIR}/")
    for p in written[:10]:
        print(f"   {p}")
    if len(written) > 10:
        print(f"   ... og {len(written) - 10} flere")


if __name__ == "__main__":
    main()