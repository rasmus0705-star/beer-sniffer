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
from urllib.parse import quote
from app.utils.slugify import clean_name, is_valid_brewery, strip_accents
from app.services.matching import _norm_brewery

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


def render_related_card(beer):
    name = escape(clean_name(beer.get("name", "")))
    slug = beer["slug"]
    image = beer.get("image") or ""
    min_price = beer.get("min_price") or 0
    img_html = (
        f'<img src="{escape(image)}" alt="{name}" loading="lazy">'
        if image else '<div class="related-img-placeholder">🍺</div>'
    )
    return f"""
    <a class="related-card" href="{SITE_URL}/ol/{slug}/">
        {img_html}
        <div class="related-name">{name}</div>
        <div class="related-price">{format_price(min_price)} kr</div>
    </a>"""


def render_price_chart(history):
    """Genererer en simpel SVG-linjegraf ud fra prishistorik — ingen
    JS-bibliotek nødvendigt, alt tegnes som ren SVG ved build-tid."""
    if not history or len(history) < 2:
        return ""

    prices = [h["price"] for h in history]
    min_p, max_p = min(prices), max(prices)
    span = (max_p - min_p) or 1
    w, h = 320, 90
    pad = 8
    n = len(prices)

    points = []
    for i, p in enumerate(prices):
        x = pad + (i / (n - 1)) * (w - 2 * pad) if n > 1 else pad
        y = pad + (1 - (p - min_p) / span) * (h - 2 * pad)
        points.append((x, y))

    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    last_x, last_y = points[-1]

    start_date = history[0]["date"]
    end_date = history[-1]["date"]

    return f"""
    <div class="chart-section">
        <div class="chart-heading">📈 Prisudvikling ({start_date} – {end_date})</div>
        <svg viewBox="0 0 {w} {h}" class="price-chart" preserveAspectRatio="none">
            <polyline points="{polyline}" fill="none" style="stroke: var(--gold); stroke-width: 2;" />
            <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="3.5" style="fill: var(--gold-light);" />
        </svg>
        <div class="chart-range">
            <span>Laveste: {format_price(min_p)} kr</span>
            <span>Højeste: {format_price(max_p)} kr</span>
        </div>
    </div>"""


def render_page(beer, updated_at, brewery_index, type_index, history_map):
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

    # ── Relaterede øl: samme bryggeri først, ellers samme stilart ──
    related = []
    related_from_brewery = False
    if is_valid_brewery(beer.get("brewery")):
        key = _norm_brewery(beer.get("brewery"))
        related = [b for b in brewery_index.get(key, []) if b.get("slug") != slug][:24]
        if related:
            related_from_brewery = True
    if not related and beer.get("type"):
        related = [b for b in type_index.get(beer["type"], []) if b.get("slug") != slug][:24]
    related_heading = (
        f"Flere øl fra {brewery}" if related and related_from_brewery
        else f"Andre {beer_type}-øl" if related else ""
    )

    page_title = f"{name} – {format_price(min_price)} kr | BeerSniffer"
    real_description = beer.get("description")
    if real_description:
        description_text = (
            real_description[:155].rsplit(" ", 1)[0] + "…"
            if len(real_description) > 155 else real_description
        )
    else:
        meta_desc_parts = [name]
        if brewery:
            meta_desc_parts.append(f"fra {brewery}")
        meta_desc_parts.append(
            f"– sammenlign priser hos {shop_count} butik{'ker' if shop_count != 1 else ''}. "
            f"Billigste pris: {format_price(min_price)} kr."
        )
        description_text = " ".join(meta_desc_parts)
    meta_description = escape(description_text)

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
    chart_html = render_price_chart(history_map.get(slug, []))

    untappd_query_name = display_name
    untappd_query = quote(untappd_query_name)

    schema = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": display_name,
        "image": image or None,
        "description": description_text,
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

    breadcrumb_schema = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "BeerSniffer", "item": f"{SITE_URL}/"},
            {"@type": "ListItem", "position": 2, "name": display_name, "item": canonical},
        ],
    }
    breadcrumb_json = json.dumps(breadcrumb_schema, ensure_ascii=False)

    image_html = (
        f'<div class="beer-image-col">'
        f'<div class="beer-image-wrap" onclick="openLightbox(\'{escape(image)}\', \'{escape(display_name)}\')">'
        f'<img class="beer-image" src="{escape(image)}" alt="{name}" loading="eager"></div>'
        f'<button class="zoom-link" onclick="openLightbox(\'{escape(image)}\', \'{escape(display_name)}\')">🔍 Se i fuld størrelse</button>'
        f'</div>'
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
<link rel="icon" href="{SITE_URL}/favicon.ico">
<meta property="og:site_name" content="BeerSniffer">
<meta property="og:title" content="{escape(page_title)}">
<meta property="og:description" content="{meta_description}">
<meta property="og:type" content="product">
<meta property="og:url" content="{canonical}">
{f'<meta property="og:image" content="{escape(image)}">' if image else ''}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{escape(page_title)}">
<meta name="twitter:description" content="{meta_description}">
{f'<meta name="twitter:image" content="{escape(image)}">' if image else ''}
<script type="application/ld+json">{schema_json}</script>
<script type="application/ld+json">{breadcrumb_json}</script>
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
.beer-image-col, .beer-image-placeholder {{
    width: 140px; flex-shrink: 0; display: flex; flex-direction: column; gap: 0.4rem;
}}
.beer-image-placeholder {{
    height: 140px; background: var(--surface2); border-radius: 12px;
    align-items: center; justify-content: center; font-size: 3rem; box-sizing: border-box;
}}
.beer-image-wrap {{
    width: 140px; height: 140px; background: var(--surface2); border-radius: 12px;
    padding: 0.8rem; box-sizing: border-box; display: flex; align-items: center; justify-content: center;
}}
.beer-image {{ width: 100%; height: 100%; object-fit: contain; }}
.beer-info h1 {{ font-size: 1.3rem; line-height: 1.35; margin-bottom: 0.4rem; }}
.beer-meta {{ font-size: 0.82rem; color: var(--text-muted); margin-bottom: 0.6rem; }}
.beer-brewery {{ font-size: 0.85rem; color: var(--gold-light); }}
.about-section {{ margin: 1.2rem 0 1.5rem; font-size: 0.86rem; line-height: 1.6; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.1rem; }}
.about-heading {{ font-size: 0.7rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 0.5rem; }}
.price-rows {{ display: flex; flex-direction: column; gap: 0.6rem; margin: 1.5rem 0; }}
.price-row {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.8rem 1rem; }}
.price-row.cheapest {{ border: 2px solid var(--gold); background: linear-gradient(135deg, rgba(200,146,14,0.1), rgba(212,98,10,0.04)); }}
.price-row-shop {{ font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem; }}
.price-row-main {{ display: flex; justify-content: space-between; align-items: center; }}
.price-amount {{ font-size: 1.3rem; font-weight: 700; color: var(--gold-light); }}
.old-price {{ font-size: 0.8rem; color: #c0a878; text-decoration: line-through; margin-left: 0.5rem; }}
.discount-badge {{ background: var(--discount); color: #000; font-size: 0.65rem; font-weight: 800; padding: 0.1rem 0.4rem; border-radius: 4px; }}
.buy-btn {{ background: linear-gradient(135deg, #ffd54a, #ffb300); color: #000; font-weight: 800; padding: 0.5rem 1rem; border-radius: 7px; text-decoration: none; font-size: 0.8rem; }}
.related-section {{ margin-top: 2rem; }}
.related-heading {{ font-size: 0.9rem; font-weight: 700; color: var(--gold-light); margin-bottom: 0.8rem; }}
.related-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 0.7rem; }}
.related-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.6rem; text-decoration: none; color: var(--text); transition: border-color 0.15s; }}
.related-card:hover {{ border-color: var(--gold); }}
.related-card img, .related-img-placeholder {{ width: 100%; height: 70px; object-fit: contain; background: var(--surface2); border-radius: 6px; margin-bottom: 0.4rem; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; }}
.related-name {{ font-size: 0.72rem; line-height: 1.3; margin-bottom: 0.2rem; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 1.9em; }}
.related-price {{ font-size: 0.78rem; font-weight: 700; color: var(--gold-light); }}
.related-item {{ display: contents; }}
.related-hidden {{ display: none; }}
.related-toggle {{ display: block; margin: 0.8rem auto 0; background: var(--surface2); border: 1px solid var(--border-light); border-radius: 999px; padding: 0.45rem 1.2rem; color: var(--gold); font-family: 'DM Sans', sans-serif; font-size: 0.78rem; cursor: pointer; transition: border-color 0.15s; }}
.related-toggle:hover {{ border-color: var(--gold); color: var(--gold-light); }}
.disclaimer {{ font-size: 0.72rem; color: var(--text-muted); margin-top: 2rem; line-height: 1.6; border-top: 1px solid var(--border); padding-top: 1rem; }}
.chart-section {{ margin: 1.5rem 0; background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.1rem; }}
.chart-heading {{ font-size: 0.7rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 0.7rem; }}
.price-chart {{ width: 100%; height: 90px; display: block; }}
.chart-range {{ display: flex; justify-content: space-between; font-size: 0.72rem; color: var(--text-muted); margin-top: 0.5rem; }}
.lightbox {{
    position: fixed; inset: 0; background: rgba(5,4,2,0.94);
    display: none; align-items: center; justify-content: center;
    z-index: 99999; padding: 2rem 1rem; cursor: zoom-out;
    backdrop-filter: blur(4px);
}}
.lightbox.open {{ display: flex; }}
.lightbox img {{
    max-width: min(90vw, 700px); max-height: 85vh; object-fit: contain;
    border-radius: 12px; box-shadow: 0 20px 60px rgba(0,0,0,0.7);
}}
.lightbox-close {{
    position: fixed; top: 1rem; right: 1.2rem; width: 44px; height: 44px;
    border-radius: 50%; background: rgba(20,16,9,0.9); border: 1px solid var(--border-light);
    color: var(--text); font-size: 1.4rem; display: flex; align-items: center;
    justify-content: center; cursor: pointer;
}}
.beer-image {{ transition: transform 0.15s; pointer-events: none; }}
.beer-image-wrap {{ cursor: zoom-in; }}
.beer-image-wrap:hover .beer-image {{ transform: scale(1.03); }}
.zoom-link {{
    background: var(--surface); border: 1px solid var(--border-light); color: var(--text-muted);
    border-radius: 7px; padding: 0.4rem 0.3rem; font-size: 0.66rem; cursor: pointer;
    font-family: 'DM Sans', sans-serif; text-align: center; width: 100%;
}}
.zoom-link:hover {{ border-color: var(--gold); color: var(--gold-light); }}
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

    {f'''<div class="about-section">
        <div class="about-heading">Om øllet</div>
        {escape(real_description)}
    </div>''' if real_description else ''}

    <div class="price-rows">
        {price_rows_html}
    </div>

    {chart_html}

    <p style="font-size:0.8rem;color:var(--text-muted)">
        Se også <a href="https://untappd.com/search?q={untappd_query}" target="_blank" rel="noopener" style="color:var(--gold)">{name} på Untappd</a>
    </p>

    {f'''<div class="related-section">
        <div class="related-heading">{escape(related_heading)}</div>
        <div class="related-grid">{"".join(f'<div class="related-item{"  related-hidden" if i >= 6 else ""}">{render_related_card(r)}</div>' for i, r in enumerate(related))}</div>
        {f'<button class="related-toggle" onclick="this.previousElementSibling.querySelectorAll(&quot;.related-hidden&quot;).forEach(e=>e.style.display=&quot;contents&quot;);this.style.display=&quot;none&quot;">Vis alle ({len(related)})</button>' if len(related) > 6 else ''}
    </div>''' if related else ''}

    <div class="disclaimer">
        📢 Affiliate disclosure: BeerSniffer kan modtage provision når du køber via vores links.
        Priser opdateret {updated_at}. Tjek altid den endelige pris hos forhandleren før køb.
    </div>
</div>

{f'''<div class="lightbox" id="lightbox" onclick="closeLightbox()">
    <button class="lightbox-close" onclick="event.stopPropagation();closeLightbox()" aria-label="Luk">✕</button>
    <img id="lightbox-img" src="" alt="">
</div>
<script>
function openLightbox(src, alt) {{
    const lb = document.getElementById('lightbox');
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox-img').alt = alt;
    lb.classList.add('open');
    document.body.style.overflow = 'hidden';
}}
function closeLightbox() {{
    document.getElementById('lightbox').classList.remove('open');
    document.body.style.overflow = '';
}}
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeLightbox(); }});
</script>''' if image else ''}
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

    try:
        with open("price_history.json", encoding="utf-8") as f:
            history_map = json.load(f)
        print(f"Prishistorik indlæst for {len(history_map)} øl.")
    except FileNotFoundError:
        history_map = {}
        print("Ingen price_history.json fundet — sider genereres uden graf.")

    if not all_mode:
        beers_to_render = beers[:limit]
        print(f"TEST-TILSTAND: genererer kun {len(beers_to_render)} sider (brug --all for alle {len(data.get('beers', []))}).")
    else:
        beers_to_render = beers
        print(f"Genererer {len(beers_to_render)} sider...")

    # Indekser til "relaterede øl" bygges ud fra ALLE øl (ikke kun test-batchen),
    # så relaterede forslag er retvisende selv i test-tilstand.
    brewery_index = {}
    type_index = {}
    for b in beers:
        if is_valid_brewery(b.get("brewery")):
            key = _norm_brewery(b["brewery"])
            brewery_index.setdefault(key, []).append(b)
        if b.get("type"):
            type_index.setdefault(b["type"], []).append(b)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    written = []
    for beer in beers_to_render:
        slug = beer["slug"]
        page_dir = os.path.join(OUTPUT_DIR, slug)
        os.makedirs(page_dir, exist_ok=True)
        html = render_page(beer, updated_at_display, brewery_index, type_index, history_map)
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