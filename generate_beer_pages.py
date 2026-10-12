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

SITE_URL = "https://beersniffer.dk"
OUTPUT_DIR = "ol"

# Tyndt ølglas-ikon (erstatter emojien)
_BEER_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 11h1a3 3 0 0 1 0 6h-1"/><path d="M9 12v6"/><path d="M13 12v6"/>'
             '<path d="M14 7.5c-1 0-1.44.5-3 .5s-2-.5-3-.5-1.72.5-2.5.5a2.5 2.5 0 0 1 0-5c.78 0 1.57.5 2.5.5S9.44 2 11 2s2 1.5 3 1.5 1.72-.5 2.5-.5a2.5 2.5 0 0 1 0 5c-.78 0-1.5-.5-2.5-.5Z"/>'
             '<path d="M5 8v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V8"/></svg>')


def load_data():
    with open("data.json", encoding="utf-8") as f:
        return json.load(f)


def format_price(p):
    """Danske priser: 18 (hele tal), 10,95 (ellers), tusindtalsseparator: 1.350"""
    n = float(p or 0)
    if abs(n - round(n)) < 0.005:
        return f"{round(n):,}".replace(",", ".")
    return f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


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
        if image else f'<div class="related-img-placeholder">{_BEER_SVG}</div>'
    )
    return f"""
    <a class="related-card" href="{SITE_URL}/ol/{slug}/">
        <span class="rc-photo">{img_html}</span>
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
        <div class="chart-heading">Prisudvikling ({start_date} – {end_date})</div>
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
    # Link til bryggeri-side, men KUN hvis bryggeriet har 2+ oel (siden findes)
    brewery_url = ""
    if is_valid_brewery(beer.get("brewery")):
        _bkey = _norm_brewery(beer.get("brewery"))
        if len(brewery_index.get(_bkey, [])) >= 2:
            from app.utils.slugify import slugify as _slugify
            brewery_url = f"{SITE_URL}/bryggeri/{_slugify(beer['brewery'])}/"

    page_title = f"{name} – {format_price(min_price)} kr | BeerSniffer"
    real_description = beer.get("description")
    _pris = format_price(min_price)
    _butik = beer.get("shop") or ""
    if shop_count > 1:
        description_text = (
            f"Sammenlign priser på {name} hos {shop_count} butikker. "
            f"Billigst lige nu: {_pris} kr" + (f" hos {_butik}" if _butik else "")
            + ". Opdateret dagligt på BeerSniffer."
        )
    else:
        description_text = (
            f"{name} til {_pris} kr" + (f" hos {_butik}" if _butik else "")
            + ". Se pris og prishistorik – opdateret dagligt på BeerSniffer."
        )
    meta_description = escape(description_text)

    canonical = f"{SITE_URL}/ol/{slug}/"

    meta_bits = []
    if beer_type:
        meta_bits.append(beer_type)
    if volume:
        meta_bits.append(f"{volume:.0f} cl")
    if abv is not None:
        meta_bits.append(f"{str(abv).replace('.', ',')}% ABV")
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
        f'<button class="zoom-link" onclick="openLightbox(\'{escape(image)}\', \'{escape(display_name)}\')">Se i fuld størrelse</button>'
        f'</div>'
        if image else f'<div class="beer-image-placeholder">{_BEER_SVG}</div>'
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
<meta name="theme-color" content="#08070a">
<link rel="preload" href="/fonts/playfair-display-latin-wght-normal.woff2" as="font" type="font/woff2" crossorigin>
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
@font-face{{font-family:'DM Sans';font-weight:100 1000;font-display:swap;src:url('/fonts/dm-sans-latin-wght-normal.woff2') format('woff2')}}
@font-face{{font-family:'Playfair Display';font-weight:400 900;font-display:swap;src:url('/fonts/playfair-display-latin-wght-normal.woff2') format('woff2')}}
:root{{--bg:#08070a;--surface:#100d11;--surface2:#16121a;--border:rgba(217,162,51,.16);--border-light:rgba(217,162,51,.32);--text:#f0e8d8;--text-muted:#a39887;--dim:#7a7064;--gold:#d9a233;--gold-light:#f0c35e;--amber:#e0a030;--accent:#e0a030;--discount:#7cc79a;--photo:#efe6d3;--serif:'Playfair Display',Georgia,serif}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:var(--bg);color:var(--text);font-family:'DM Sans',system-ui,sans-serif;min-height:100vh;-webkit-font-smoothing:antialiased}}
a:focus-visible,button:focus-visible{{outline:2px solid var(--gold);outline-offset:2px}}
.bar{{position:sticky;top:0;z-index:50;display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:.5rem 1.5rem;background:rgba(8,7,10,.88);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border-bottom:1px solid var(--border)}}
.brand{{display:flex;align-items:center;gap:.7rem;text-decoration:none}}
.brand img{{height:40px;width:auto;display:block}}
.brand span{{font-family:var(--serif);font-weight:500;font-size:1rem;letter-spacing:.32em;text-transform:uppercase;color:var(--gold-light)}}
.back-link{{font-size:.66rem;letter-spacing:.18em;text-transform:uppercase;color:var(--text-muted);text-decoration:none;white-space:nowrap}}
.back-link:hover{{color:var(--gold-light)}}
.wrap{{max-width:860px;margin:0 auto;padding:2rem 1.5rem 3rem}}
.beer-header{{display:flex;gap:2rem;margin-bottom:2rem;align-items:flex-start}}
.beer-image-col,.beer-image-placeholder{{width:200px;flex-shrink:0;display:flex;flex-direction:column;gap:.5rem}}
.beer-image-placeholder{{height:240px;background:var(--photo);border-radius:4px;align-items:center;justify-content:center}}
.beer-image-placeholder svg,.related-img-placeholder svg{{width:2.6rem;height:2.6rem;fill:none;stroke:#b9a577;stroke-width:1.4;stroke-linecap:round;stroke-linejoin:round}}
.beer-image-wrap{{width:200px;height:240px;background:var(--photo);border-radius:4px;padding:1rem;display:flex;align-items:center;justify-content:center;cursor:zoom-in}}
.beer-image{{width:100%;height:100%;object-fit:contain;mix-blend-mode:multiply;transition:transform .15s;pointer-events:none}}
.beer-image-wrap:hover .beer-image{{transform:scale(1.03)}}
.zoom-link{{background:none;border:0;color:var(--dim);font-family:'DM Sans',sans-serif;font-size:.6rem;letter-spacing:.16em;text-transform:uppercase;cursor:pointer;text-align:left;padding:0}}
.zoom-link:hover{{color:var(--gold-light)}}
.beer-info{{display:flex;flex-direction:column;min-width:0}}
.beer-brewery{{order:-1;font-size:.62rem;letter-spacing:.3em;text-transform:uppercase;color:var(--accent);margin-bottom:.6rem}}
.beer-brewery a{{color:var(--accent);text-decoration:none}}
.beer-brewery a:hover{{color:var(--gold-light)}}
.beer-info h1{{font-family:var(--serif);font-weight:500;font-size:clamp(1.6rem,3.6vw,2.4rem);line-height:1.15;letter-spacing:-.01em;margin-bottom:.7rem;text-wrap:balance}}
.beer-meta{{font-size:.82rem;color:var(--text-muted);letter-spacing:.04em}}
.about-section{{margin:1.4rem 0 1.8rem;font-size:.92rem;line-height:1.7;color:var(--text-muted);background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:1.1rem 1.25rem}}
.about-heading{{font-size:.6rem;letter-spacing:.26em;text-transform:uppercase;color:var(--accent);margin-bottom:.6rem}}
.price-rows{{display:flex;flex-direction:column;gap:.6rem;margin:1.6rem 0}}
.price-row{{background:transparent;border:1px solid var(--border);border-radius:2px;padding:.9rem 1.1rem}}
.price-row.cheapest{{border:1px solid var(--gold);background:rgba(217,162,51,.045)}}
.price-row-shop{{font-size:.62rem;text-transform:uppercase;letter-spacing:.16em;color:var(--text-muted);margin-bottom:.5rem;display:flex;align-items:center;gap:.6rem}}
.price-row.cheapest .price-row-shop{{color:var(--gold-light)}}
.price-row-main{{display:flex;justify-content:space-between;align-items:center;gap:1rem}}
.price-amount{{font-family:var(--serif);font-size:1.7rem;font-weight:500;color:var(--text);font-variant-numeric:tabular-nums}}
.price-row.cheapest .price-amount{{color:var(--gold-light)}}
.old-price{{font-size:.8rem;color:var(--dim);text-decoration:line-through;text-decoration-color:rgba(163,152,135,.55);margin-left:.6rem}}
.discount-badge{{background:transparent;color:var(--discount);border:1px solid rgba(124,199,154,.4);font-size:.62rem;font-weight:600;padding:.1rem .45rem;border-radius:2px;letter-spacing:.04em}}
.buy-btn{{background:transparent;border:1px solid var(--gold);color:var(--gold-light);font-weight:600;padding:.6rem 1.3rem;border-radius:2px;text-decoration:none;font-size:.68rem;letter-spacing:.16em;text-transform:uppercase;white-space:nowrap}}
.buy-btn:hover{{background:var(--gold);color:#0a0806}}
.related-section{{margin-top:2.4rem}}
.related-heading{{font-family:var(--serif);font-size:1.2rem;font-weight:500;color:var(--gold-light);letter-spacing:.03em;margin-bottom:1rem}}
.related-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:.8rem}}
.related-card{{background:var(--surface);border:1px solid var(--border);border-radius:4px;text-decoration:none;color:var(--text);transition:border-color .15s;overflow:hidden;display:flex;flex-direction:column}}
.related-card:hover{{border-color:var(--gold)}}
.rc-photo{{display:flex;align-items:center;justify-content:center;background:var(--photo);height:110px;padding:.5rem}}
.rc-photo img{{max-width:100%;max-height:100%;width:auto;height:auto;object-fit:contain;mix-blend-mode:multiply;display:block}}
.related-name{{font-family:var(--serif);font-weight:500;font-size:.82rem;line-height:1.3;padding:.6rem .7rem 0;min-height:3.2em;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.related-price{{font-family:var(--serif);font-size:1rem;font-weight:500;color:var(--gold-light);padding:.25rem .7rem .7rem;margin-top:auto;font-variant-numeric:tabular-nums}}
.related-item{{display:contents}}
.related-hidden{{display:none}}
.related-toggle{{display:block;margin:1rem auto 0;background:transparent;border:1px solid var(--border-light);border-radius:2px;padding:.55rem 1.3rem;color:var(--gold-light);font-family:'DM Sans',sans-serif;font-size:.64rem;letter-spacing:.16em;text-transform:uppercase;cursor:pointer}}
.related-toggle:hover{{border-color:var(--gold);background:rgba(217,162,51,.07)}}
.disclaimer{{font-size:.72rem;color:var(--dim);margin-top:2.4rem;line-height:1.6;border-top:1px solid var(--border);padding-top:1rem}}
.chart-section{{margin:1.6rem 0;background:var(--surface);border:1px solid var(--border);border-radius:4px;padding:1rem 1.2rem}}
.chart-heading{{font-size:.6rem;letter-spacing:.26em;text-transform:uppercase;color:var(--accent);margin-bottom:.8rem}}
.price-chart{{width:100%;height:90px;display:block}}
.chart-range{{display:flex;justify-content:space-between;font-size:.72rem;color:var(--text-muted);margin-top:.5rem}}
.lightbox{{position:fixed;inset:0;background:rgba(5,4,6,.95);display:none;align-items:center;justify-content:center;z-index:99999;padding:2rem 1rem;cursor:zoom-out;backdrop-filter:blur(4px)}}
.lightbox.open{{display:flex}}
.lightbox img{{max-width:min(90vw,700px);max-height:85vh;object-fit:contain;border-radius:4px;box-shadow:0 20px 60px rgba(0,0,0,.7);background:var(--photo)}}
.lightbox-close{{position:fixed;top:1rem;right:1.2rem;width:44px;height:44px;border-radius:50%;background:rgba(16,13,17,.9);border:1px solid var(--border-light);color:var(--text);font-size:1.4rem;display:flex;align-items:center;justify-content:center;cursor:pointer}}
@media(max-width:560px){{.bar{{padding:.45rem 1rem}}.brand span{{font-size:.82rem;letter-spacing:.22em}}.back-link{{font-size:.6rem;letter-spacing:.12em}}.wrap{{padding:1.4rem 1rem 2rem}}.beer-header{{gap:1.1rem}}.beer-image-col,.beer-image-placeholder{{width:120px}}.beer-image-wrap{{width:120px;height:150px;padding:.6rem}}.beer-image-placeholder{{height:150px}}.price-amount{{font-size:1.45rem}}.related-grid{{grid-template-columns:repeat(2,1fr)}}}}
</style>
</head>
<body>
<header class="bar">
    <a class="brand" href="{SITE_URL}/"><img src="{SITE_URL}/logo-hero.png" alt="" width="48" height="40"><span>BeerSniffer</span></a>
    <a class="back-link" href="{SITE_URL}/">← Alle øltilbud</a>
</header>
<main class="wrap">
    <div class="beer-header">
        {image_html}
        <div class="beer-info">
            <h1>{name}</h1>
            {f'<div class="beer-brewery"><a href="{brewery_url}">{brewery}</a></div>' if brewery and brewery_url else (f'<div class="beer-brewery">{brewery}</div>' if brewery else '')}
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
        Affiliate disclosure: BeerSniffer kan modtage provision når du køber via vores links.
        Priser opdateret {updated_at}. Tjek altid den endelige pris hos forhandleren før køb.
    </div>
</main>

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