# -*- coding: utf-8 -*-
"""generate_brewery_pages.py -- bryggeri-sider (bryggeri/{slug}/).
  python generate_brewery_pages.py            -> KUN test-bryggeri (Thisted)
  python generate_brewery_pages.py --all      -> ALLE bryggerier med 2+ oel
"""
import os, sys, json, html as _html
from html import escape

from generate_beer_pages import (
    SITE_URL, load_data, format_price, render_related_card
)
from app.services.matching import _norm_brewery
from app.utils.slugify import is_valid_brewery, slugify

ALL = "--all" in sys.argv
OUTDIR = "bryggeri"
TEST_BREWERY = "Thisted Bryghus"


def brewery_slug(navn):
    return slugify(navn)


def _stats(beers):
    priser = [b.get("min_price") for b in beers if b.get("min_price")]
    stilarter = sorted({b.get("type") for b in beers if b.get("type")})
    billigst = min(priser) if priser else 0
    gns = round(sum(priser) / len(priser)) if priser else 0
    rabat = max((b.get("max_discount_pct") or 0) for b in beers) if beers else 0
    return billigst, gns, rabat, stilarter


def _intro(navn, antal, billigst, stilarter):
    stil_txt = ""
    if len(stilarter) >= 3:
        stil_txt = f" Udvalget fra {navn} spaender over {', '.join(stilarter[:3]).lower()} og flere stilarter."
    elif stilarter:
        stil_txt = f" Udvalget taeller bl.a. {stilarter[0].lower()}."
    return (f"Se alle {antal} \u00f8l fra {navn} og sammenlign priser p\u00e5 tv\u00e6rs af danske "
            f"\u00f8lbutikker.{stil_txt} Billigste \u00f8l fra {navn} koster lige nu "
            f"{format_price(billigst)} kr \u2014 opdateret dagligt p\u00e5 BeerSniffer.")


def render_brewery_page(navn, beers):
    beers = sorted(beers, key=lambda b: b.get("min_price") or 9999)
    antal = len(beers)
    billigst, gns, rabat, stilarter = _stats(beers)
    slug = brewery_slug(navn)
    navn_esc = escape(navn)
    intro = _intro(navn_esc, antal, billigst, stilarter)
    canonical = f"{SITE_URL}/{OUTDIR}/{slug}/"

    cards = "".join(f'<div class="related-item">{render_related_card(b)}</div>' for b in beers)

    return f"""<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{navn_esc} \u00f8l \u2013 priser og tilbud | BeerSniffer</title>
<meta name="description" content="{escape(intro)[:155]}">
<link rel="canonical" href="{canonical}">
<link rel="icon" href="{SITE_URL}/favicon.ico">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Fraunces:wght@600;700&display=swap" rel="stylesheet">
<style>
:root {{ --bg:#0f0d0a; --surface:#1a1613; --surface2:#241f1a; --border:#2e2822; --border-light:#3a332b; --text:#f0e9df; --gold:#c8920e; --gold-light:#e0b53a; --muted:#9a8f80; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:var(--bg); color:var(--text); font-family:'DM Sans',sans-serif; min-height:100vh; }}
.wrap {{ max-width:960px; margin:0 auto; padding:1.5rem; }}
.site-logo-link {{ display:inline-flex; align-items:center; gap:0.8rem; text-decoration:none; margin-bottom:1.4rem; }}
.site-logo {{ height:68px; width:auto; filter:drop-shadow(0 3px 14px rgba(200,146,14,0.45)); }}
.back-link {{ color:var(--gold); text-decoration:none; font-size:0.85rem; }}
.brewery-title {{ font-family:'Fraunces',serif; font-size:2.1rem; color:var(--gold-light); margin-bottom:0.6rem; }}
.brewery-intro {{ color:var(--text); font-size:1rem; line-height:1.6; max-width:700px; margin-bottom:1.4rem; }}
.stats {{ display:flex; flex-wrap:wrap; gap:0.8rem; margin-bottom:1.8rem; }}
.stat {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:0.7rem 1.1rem; }}
.stat-num {{ font-size:1.3rem; font-weight:700; color:var(--gold-light); }}
.stat-label {{ font-size:0.72rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.03em; }}
.related-grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:0.8rem; align-items:stretch; }}
.related-item {{ display:flex; }}
.related-card {{ background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:0.6rem; text-decoration:none; color:var(--text); transition:border-color 0.15s; overflow:hidden; display:flex; flex-direction:column; width:100%; }}
.related-card:hover {{ border-color:var(--gold); }}
.related-card img {{ width:100%; height:120px; object-fit:contain; background:var(--surface2); border-radius:6px; margin-bottom:0.4rem; display:block; }}
.related-img-placeholder {{ width:100%; height:120px; background:var(--surface2); border-radius:6px; margin-bottom:0.4rem; display:flex; align-items:center; justify-content:center; font-size:1.6rem; }}
.related-name {{ font-size:0.8rem; line-height:1.3; margin-bottom:0.3rem; min-height:2.1em; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }}
.related-price {{ font-size:0.9rem; font-weight:700; color:var(--gold-light); line-height:1.4; padding-bottom:0.2rem; margin-top:auto; }}
</style>
</head>
<body>
<div class="wrap">
    <a class="site-logo-link" href="{SITE_URL}/">
        <img src="{SITE_URL}/logo.png" alt="BeerSniffer" class="site-logo">
        <span class="back-link">\u2190 Alle \u00f8ltilbud</span>
    </a>
    <h1 class="brewery-title">{navn_esc}</h1>
    <p class="brewery-intro">{escape(intro)}</p>
    <div class="stats">
        <div class="stat"><div class="stat-num">{antal}</div><div class="stat-label">\u00f8l</div></div>
        <div class="stat"><div class="stat-num">{format_price(billigst)} kr</div><div class="stat-label">billigst</div></div>
        <div class="stat"><div class="stat-num">{format_price(gns)} kr</div><div class="stat-label">gennemsnit</div></div>
        <div class="stat"><div class="stat-num">-{round(rabat)}%</div><div class="stat-label">stoerste rabat</div></div>
    </div>
    <div class="related-grid">{cards}</div>
</div>
</body>
</html>"""


def main():
    data = load_data()
    beers = data.get("beers", data)

    idx = {}
    for b in beers:
        if is_valid_brewery(b.get("brewery")):
            idx.setdefault(_norm_brewery(b["brewery"]), []).append(b)

    display = {}
    for key, grp in idx.items():
        display[key] = min((x.get("brewery") for x in grp), key=len)

    if ALL:
        targets = {k: v for k, v in idx.items() if len(v) >= 2}
    else:
        tkey = _norm_brewery(TEST_BREWERY)
        targets = {tkey: idx.get(tkey, [])} if idx.get(tkey) else {}
        if not targets:
            print(f"Fandt ikke test-bryggeriet {TEST_BREWERY!r}."); return

    os.makedirs(OUTDIR, exist_ok=True)

    # Ryd forael­dede bryggeri-mapper (bryggerier der ikke laengere har 2+ oel)
    if ALL:
        gyldige = {brewery_slug(display[k]) for k in targets}
        for d in os.listdir(OUTDIR):
            sti = os.path.join(OUTDIR, d)
            if os.path.isdir(sti) and d not in gyldige:
                import shutil
                shutil.rmtree(sti)

    n = 0
    for key, grp in targets.items():
        navn = display[key]
        page = render_brewery_page(navn, grp)
        d = os.path.join(OUTDIR, brewery_slug(navn))
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "index.html"), "w", encoding="utf-8") as f:
            f.write(page)
        n += 1
    print(f"Skrev {n} bryggeri-side(r) til {OUTDIR}/")
    if not ALL:
        print(f"Test: aabn bryggeri\\{brewery_slug(display[_norm_brewery(TEST_BREWERY)])}\\index.html")


if __name__ == "__main__":
    main()