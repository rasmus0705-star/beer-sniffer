"""
patch_internal_links.py

Ændrer ølkortene på forsiden så BILLEDE og NAVN linker til jeres egen
/ol/{slug}/-side i stedet for direkte ud til butikken. "Køb →"-knappen
(og alle andre køb-knapper) rører vi IKKE — de skal stadig gå direkte
til butikken, det er dem der tjener penge.

Kør fra roden af dit projekt (samme sted som index.html):
    python patch_internal_links.py
"""

import shutil
import sys
from pathlib import Path

TARGET = Path("index.html")

if not TARGET.exists():
    print(f"FEJL: Finder ikke {TARGET.resolve()} — kør scriptet i samme mappe som index.html")
    sys.exit(1)

backup = TARGET.with_suffix(".html.bak4")
shutil.copy(TARGET, backup)
print(f"Backup gemt som: {backup}")

text = TARGET.read_text(encoding="utf-8")


def apply(old, new, label):
    global text
    count = text.count(old)
    if count == 0:
        print(f"  [SPRINGET OVER] Fandt ikke tekst til: {label} — tjek om filen allerede er ændret.")
        return False
    if count > 1:
        print(f"  [ADVARSEL] Teksten til '{label}' findes {count} gange — springer over for sikkerheds skyld.")
        return False
    text = text.replace(old, new)
    print(f"  [OK] {label}")
    return True


# 1) CSS: sørg for at card-name ikke ser ud som et almindeligt blåt link
apply(
    """        .card-name {
            font-size: 0.88rem;
            font-weight: 600;
            line-height: 1.3;
            color: var(--text);
            margin-bottom: 0.5rem;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            min-height: 2.3em;
        }""",
    """        .card-name {
            font-size: 0.88rem;
            font-weight: 600;
            line-height: 1.3;
            color: var(--text);
            margin-bottom: 0.5rem;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
            min-height: 2.3em;
            text-decoration: none;
        }
        .card-name:hover { color: var(--gold-light); }""",
    "CSS: card-name ser ikke ud som et link, men reagerer på hover",
)

# 2) JS: beregn intern URL FØR billedet bygges
apply(
    """        const untappdQuery = encodeURIComponent((() => { const n = b.name.replace(/\\d+[.,]?\\d*\\s?%/g,'').replace(/\\d+\\s?(cl|ml)/gi,'').trim(); return n.split(/\\s+/).slice(0,4).join(' ').trim(); })());

        let html = `<div class="card${maxDiscount > 0 ? ' has-deal' : ''}" style="animation-delay:${delay}s" role="listitem">`;""",
    """        const untappdQuery = encodeURIComponent((() => { const n = b.name.replace(/\\d+[.,]?\\d*\\s?%/g,'').replace(/\\d+\\s?(cl|ml)/gi,'').trim(); return n.split(/\\s+/).slice(0,4).join(' ').trim(); })());
        const detailUrl = b.slug ? `ol/${b.slug}/` : (best.url || '#');
        const detailTarget = b.slug ? '' : ' target="_blank"';

        let html = `<div class="card${maxDiscount > 0 ? ' has-deal' : ''}" style="animation-delay:${delay}s" role="listitem">`;""",
    "JS: beregn intern detail-URL pr. øl",
)

# 3) JS: billedet linker nu til den interne side, ikke direkte til butikken
apply(
    """        html += `<a class="card-img-wrap" ${best.url ? `href="${best.url}" target="_blank" onclick="gtag('event','billede_klik',{beer_name:'${bName}',shop:'${bShop}',price:${minPrice}})"` : ''} aria-label="${b.name} — køb hos ${best.shop_name || 'butik'}">`;""",
    """        html += `<a class="card-img-wrap" href="${detailUrl}"${detailTarget} onclick="gtag('event','produkt_klik',{beer_name:'${bName}',shop:'${bShop}',price:${minPrice}})" aria-label="Se ${b.name} hos BeerSniffer">`;""",
    "JS: billede linker til intern side",
)

# 4) JS: navnet bliver et rigtigt link til den interne side
apply(
    """        html += `<div class="card-body"><div class="card-name">${b.name}</div>`;""",
    """        html += `<div class="card-body"><a class="card-name" href="${detailUrl}"${detailTarget}>${b.name}</a>`;""",
    "JS: ølnavn bliver klikbart link til intern side",
)

TARGET.write_text(text, encoding="utf-8")
print(f"\nFærdig! {TARGET} er opdateret. Original ligger i {backup}")