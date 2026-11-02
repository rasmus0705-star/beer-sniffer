#!/usr/bin/env python3
"""Render current BeerSniffer stats and featured offers into the homepage HTML."""
from __future__ import annotations

import html
import json
import re
from pathlib import Path
from datetime import datetime


ROOT = Path(__file__).resolve().parent


def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def fmt_price(value: object) -> str:
    amount = float(value or 0)
    return (f"{amount:.0f}" if amount.is_integer() else f"{amount:.2f}").replace(".", ",")


def main() -> None:
    data = json.loads((ROOT / "data.json").read_text(encoding="utf-8"))
    stats = data.get("stats", {})
    beers = data.get("beers", [])
    page = (ROOT / "index.html").read_text(encoding="utf-8")
    total = int(stats.get("total", len(beers)))
    shops = int(stats.get("shops", len(stats.get("shop_names", []))))
    max_abv = max((float(b.get("abv") or 0) for b in beers), default=15)
    max_abv = max(15, int(max_abv * 2 + 0.999) / 2)
    description = f"Sammenlign priser på {total:,}+ øl fra {shops} danske webshops. Find dagens bedste øltilbud — opdateres dagligt.".replace(",", ".")
    page = re.sub(r'<meta name="description" content="[^"]*">', f'<meta name="description" content="{esc(description)}">', page, count=1)
    page = re.sub(r'<meta property="og:description" content="[^"]*">', f'<meta property="og:description" content="{esc(description)}">', page, count=1)
    page = re.sub(r'(<input type="range" id="abv-min"[^>]*max=")[^"]+', rf'\g<1>{max_abv:g}', page, count=1)
    page = re.sub(r'(<input type="range" id="abv-max"[^>]*max=")[^"]+', rf'\g<1>{max_abv:g}', page, count=1)
    page = re.sub(r'(<input type="range" id="abv-max"[^>]*value=")[^"]+', rf'\g<1>{max_abv:g}', page, count=1)
    page = re.sub(r'(<div class="range-val" id="abv-val"[^>]*>)[^<]+', rf'\g<1>0–{max_abv:g}%', page, count=1)

    values = {
        "brand-shop-count": str(stats.get("shops", len(stats.get("shop_names", [])))),
        "hero-beer-count": f'{int(stats.get("total", len(beers))):,}'.replace(",", "."),
        "stat-total": f'{int(stats.get("total", len(beers))):,}'.replace(",", "."),
        "stat-deals": f'{int(stats.get("deals", 0)):,}'.replace(",", "."),
        "stat-max-discount": f'−{round(max((b.get("max_discount_pct") or 0 for b in beers), default=0))} %',
        "stat-cheapest": f'{stats.get("cheapest", 0):g} kr',
    }
    for element_id, value in values.items():
        page = re.sub(
            rf'(<(?:strong|div)[^>]*\bid="{re.escape(element_id)}"[^>]*>).*?(</(?:strong|div)>)',
            lambda match, value=value: match.group(1) + esc(value) + match.group(2),
            page,
            count=1,
            flags=re.DOTALL,
        )

    featured = sorted(
        (b for b in beers if (b.get("max_discount_pct") or 0) > 0 and b.get("prices")
         and b.get("category") != "smagekasse"
         and not re.search(r"smagekasse|smage kasse|mixkasse|mix kasse|prøvekasse|gavekasse|julekalender|adventskalender|julepakke|mixed pack|selection box|tasting set|beer box|sampler|variety pack|discovery", b.get("name", ""), re.I)),
        key=lambda b: b.get("max_discount_pct") or 0,
        reverse=True,
    )[:10]
    cards = []
    for beer in featured:
        prices = sorted(beer["prices"], key=lambda p: p.get("discount_pct") or 0, reverse=True)
        price = prices[0]
        amount = price.get("price_dkk", price.get("price", 0))
        product_url = "/ol/" + esc(beer.get("slug")) + "/" if beer.get("slug") else "#produkter"
        image = beer.get("image")
        image_html = f'<img class="top-card-img" src="{esc(image)}" alt="{esc(beer.get("name"))}" loading="lazy">' if image else '<div class="top-card-img-placeholder" aria-hidden="true">ØL</div>'
        old_price_html = f'<span class="top-card-old">{fmt_price(price.get("old_price"))} kr</span>' if price.get("old_price") else ""
        buy_html = f'<a class="top-card-link" href="{esc(price.get("url"))}" target="_blank" rel="sponsored noopener">Køb →</a>' if price.get("url") else ""
        cards.append(
            f'<article class="top-card" data-href="{product_url}">'
            f'<a href="{product_url}" aria-label="Se {esc(beer.get("name"))}">{image_html}</a>'
            f'<div class="top-card-body"><div class="top-card-shop">{esc(price.get("shop_name"))}</div>'
            f'<a class="top-card-name" href="{product_url}">{esc(beer.get("name"))}</a>'
            f'<div class="top-card-prices"><span class="top-card-price">{fmt_price(amount)} kr</span>'
            f'{old_price_html}</div>'
            f'<span class="top-card-pct">−{round(beer.get("max_discount_pct") or 0)} %</span>'
            f'{buy_html}'
            f'</div></article>'
        )
    static_offers = '\n'.join(cards)
    page = re.sub(
        r'(<div class="top-deals-scroll" id="top-deals-scroll">).*?(</div>\s*</div>\s*<!-- MOBILE FILTER TOGGLE -->)',
        lambda match: match.group(1) + static_offers + match.group(2),
        page,
        count=1,
        flags=re.DOTALL,
    )
    page = page.replace('id="top-deals-section" style="display:none"', 'id="top-deals-section"')

    # The static result summary and featured cards are visible to crawlers before JS runs.
    count = total
    page = page.replace('id="loading" role="status"', 'id="loading" role="status" style="display:none"')
    page = re.sub(
        r'<p class="result-count" id="result-count"[^>]*>.*?</p>',
        f'<p class="result-count" id="result-count" aria-live="polite">{count:,} øl i prissammenligningen</p>'.replace(",", "."),
        page,
        count=1,
        flags=re.DOTALL,
    )
    # Insert a compact, crawlable product sample. The client renderer replaces it after data loads.
    sample = []
    featured_slugs = {b.get("slug") for b in featured}
    sample_beers = (b for b in beers if b.get("slug") not in featured_slugs)
    for beer in sorted(sample_beers, key=lambda b: b.get("min_price") or float("inf"))[:20]:
        name = esc(beer.get("name"))
        slug = esc(beer.get("slug"))
        price = beer.get("min_price") or 0
        sample.append(f'<article class="static-beer"><a href="/ol/{slug}/">{name}</a><span>Fra {fmt_price(price)} kr</span></article>')
    page = re.sub(
        r'(<div class="grid" id="grid" role="list">).*?(</div>\s*<div style="text-align:center;margin:1.5rem 0;">)',
        lambda match: match.group(1) + ''.join(sample) + match.group(2),
        page,
        count=1,
        flags=re.DOTALL,
    )
    (ROOT / "index.html").write_text(page, encoding="utf-8")
    print(f"Homepage opdateret: {count} produkter, {stats.get('shops', 0)} butikker, {len(featured)} tilbud")


if __name__ == "__main__":
    main()
