"""
build_data.py — Lokal daglig opdatering af BeerSniffer.

Workflow:
1. Kører alle 6 scrapers
2. Gemmer i Supabase (samme som før — bevarer historik)
3. Eksporterer grupperet ølliste til data.json (frontend læser denne)

Kør med: python build_data.py
"""

import json
import sys
import subprocess
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Indlæs DB_URL fra .env
load_dotenv()

from app.database import SessionLocal
from app.models import Beer, Price, PriceHistory
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.scrapers.brygshoppen import scrape_brygshoppen
from app.scrapers.beermatch import scrape_beermatch
from app.scrapers.drikbeer import scrape_drikbeer
from app.scrapers.agoodcase import scrape_agoodcase
from app.scrapers.beershoppen import scrape_beershoppen
from app.scrapers.bestofbeers import scrape_bestofbeers
from app.scrapers.oeltanken import scrape_oeltanken
from app.scrapers.beerme import scrape_beerme
from app.scrapers.vildmedvin import scrape_vildmedvin

from app.services.ingest import ingest_batch
from app.utils.overrides import load_fejlliste, apply_overrides, write_fejlliste
from app.services.matching import (
    normalize_for_matching,
    style_fingerprint,
    styles_compatible,
    volumes_compatible,
    abv_compatible,
    breweries_compatible,
    variants_compatible,
    similarity_score,
    has_meaningful_overlap,
    required_threshold,
    MATCH_THRESHOLD,
)


def run_all_scrapers():
    """Kører alle 6 scrapers og samler items."""
    all_items = []
    results = {}

    scrapers = [
        ("Brygshoppen", scrape_brygshoppen),
        ("Beermatch", scrape_beermatch),
        ("Drikbeer", scrape_drikbeer),
        ("A Good Case", scrape_agoodcase),
        ("Beershoppen", scrape_beershoppen),
        ("Best of Beers", scrape_bestofbeers),
        ("Øltanken", scrape_oeltanken),
        ("Beer Me", scrape_beerme),
        ("Vild med Vin", scrape_vildmedvin),
    ]

    for name, func in scrapers:
        print(f"\n🍺 Kører {name}...")
        try:
            items = func()
            all_items.extend(items)
            results[name] = len(items)
            print(f"   ✅ {len(items)} produkter")
        except Exception as e:
            results[name] = f"FEJL: {e}"
            print(f"   ❌ Fejl: {e}")

    return all_items, results


def build_beer_list_from_db(db):
    """
    Genopbygger den grupperede ølliste fra databasen.
    Samme logik som beers.py /beers endpoint.
    """
    beers = db.query(Beer).options(joinedload(Beer.prices)).all()
    beers = sorted(beers, key=lambda b: len(b.prices or []), reverse=True)

    grouped = {}
    counter = 0

    for beer in beers:
        if not beer.prices:
            continue

        norm = normalize_for_matching(beer.name)
        fp = style_fingerprint(beer.name)
        vol = beer.volume_cl
        abv = beer.abv
        brewery = beer.brewery

        best_key = None
        best_score = 0.0
        best_threshold = MATCH_THRESHOLD

        for key, g in grouped.items():
            if not styles_compatible(fp, g["_fingerprint"]):
                continue
            if not volumes_compatible(vol, g.get("volume_cl")):
                continue
            if not abv_compatible(abv, g.get("abv")):
                continue
            if not breweries_compatible(brewery, g.get("brewery"), beer.name, g.get("name")):
                continue
            if not variants_compatible(beer.name, g.get("name")):
                continue
            if not has_meaningful_overlap(beer.name, g.get("name")):
                continue

            score = similarity_score(
                norm, g["_normalized"],
                abv, g.get("abv"),
                brewery, g.get("brewery"),
                fp, g["_fingerprint"],
            )

            threshold = required_threshold(
                abv, g.get("abv"),
                vol, g.get("volume_cl"),
                brewery, g.get("brewery"),
            )

            if score > best_score:
                best_score = score
                best_key = key
                best_threshold = threshold

        if best_key and best_score >= best_threshold:
            target = grouped[best_key]
            if beer.id < target["id"]:
                target["id"] = beer.id
                target["slug"] = beer.slug
            if beer.description and (
                not target.get("description")
                or len(beer.description) > len(target["description"])
            ):
                target["description"] = beer.description
            target.setdefault("_all_ids", [target["id"]]).append(beer.id)
            for p in beer.prices:
                target["prices"].append({
                    "shop_name": p.shop_name,
                    "price": p.price_dkk,
                    "url": p.url,
                    "discount_pct": p.discount_pct or 0,
                    "old_price": p.old_price if hasattr(p, "old_price") else None,
                })
            if not target.get("image") and beer.image:
                target["image"] = beer.image
            if not target.get("brewery") and brewery:
                target["brewery"] = brewery
            if not target.get("type") and beer.type:
                target["type"] = beer.type
            if target.get("abv") is None and abv is not None:
                target["abv"] = abv
            if target.get("volume_cl") is None and vol is not None:
                target["volume_cl"] = vol
            target["_fingerprint"] = target["_fingerprint"] | fp
        else:
            counter += 1
            key = f"g_{counter}"
            grouped[key] = {
                "id": beer.id,
                "slug": beer.slug,
                "description": beer.description,
                "_all_ids": [beer.id],
                "name": beer.name,
                "image": beer.image,
                "type": beer.type,
                "abv": abv,
                "volume_cl": vol,
                "brewery": brewery,
                "category": beer.category if hasattr(beer, "category") else None,
                "_normalized": norm,
                "_fingerprint": fp,
                "prices": [
                    {
                        "shop_name": p.shop_name,
                        "price": p.price_dkk,
                        "url": p.url,
                        "discount_pct": p.discount_pct or 0,
                        "old_price": p.old_price if hasattr(p, "old_price") else None,
                    }
                    for p in beer.prices
                ],
            }

    # Færdiggør hver gruppe
    result = []
    for g in grouped.values():
        # Dedupliker shops (behold billigste hvis samme shop flere gange)
        unique_shops = {}
        for p in g["prices"]:
            shop = p["shop_name"]
            if shop not in unique_shops or p["price"] < unique_shops[shop]["price"]:
                unique_shops[shop] = p

        prices = sorted(unique_shops.values(), key=lambda x: x["price"])
        if not prices:
            continue

        cheapest = prices[0]
        max_discount = max((p["discount_pct"] or 0) for p in prices)

        # Fjern interne nøgler
        g.pop("_normalized", None)
        g.pop("_fingerprint", None)

        g["prices"] = prices
        g["cheapest_price"] = cheapest["price"]
        g["min_price"] = cheapest["price"]
        g["shop"] = cheapest["shop_name"]
        g["discount_pct"] = cheapest["discount_pct"]
        g["max_discount_pct"] = max_discount

        result.append(g)

    # Sortér efter billigste pris
    result.sort(key=lambda b: b["cheapest_price"])

    return result


def build_price_history(db, beer_list, days=90, min_points=2):
    """
    Bygger price_history.json: {slug: [{date, price}, ...]}
    Én samlet forespørgsel til PriceHistory for alle relevante id'er,
    fremfor én forespørgsel pr. øl (samme performance-lektie som ingest.py).
    Viser billigste pris PÅ TVÆRS AF BUTIKKER pr. dag.
    """
    all_ids = set()
    for b in beer_list:
        all_ids.update(b.get("_all_ids", []))

    if not all_ids:
        print("   Ingen id'er fundet — springer prishistorik over")
        return

    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(PriceHistory.beer_id, PriceHistory.price_dkk, PriceHistory.created_at)
        .filter(PriceHistory.beer_id.in_(all_ids))
        .filter(PriceHistory.created_at >= cutoff)
        .all()
    )

    # beer_id -> {dato: billigste pris den dag}
    by_id = {}
    for beer_id, price, created_at in rows:
        date_str = created_at.strftime("%Y-%m-%d")
        d = by_id.setdefault(beer_id, {})
        if date_str not in d or price < d[date_str]:
            d[date_str] = price

    history_out = {}
    _implausible_drops = []
    for b in beer_list:
        slug = b.get("slug")
        ids = b.get("_all_ids", [])
        if not slug or not ids:
            continue
        merged = {}
        for bid in ids:
            for date_str, price in by_id.get(bid, {}).items():
                if date_str not in merged or price < merged[date_str]:
                    merged[date_str] = price
        if len(merged) < min_points:
            continue
        history_out[slug] = [
            {"date": d, "price": p} for d, p in sorted(merged.items())
        ]

        # Prisaendring over de seneste ~7 dage — bruges til 📉-badge
        # paa forsiden. Tidligste pris i vinduet vs. nyeste.
        _week_cutoff = (datetime.utcnow() - timedelta(days=8)).strftime("%Y-%m-%d")
        _recent = [(d, p) for d, p in sorted(merged.items()) if d >= _week_cutoff]
        if len(_recent) >= 2:
            _ref_price = _recent[0][1]
            _change = round(_recent[-1][1] - _ref_price, 2)
            if abs(_change) >= 1:
                # Plausibilitets-gate (prisloft): et aegte prisfald —
                # ogsaa store udloebsrabatter paa 80%+ — har en udgangs-
                # pris, der ligner hvad oellen faktisk koster i dag
                # (andre butikkers pris eller old_price). En falsk match
                # i historikken (kasse vs. enkeltdaase) har en udgangs-
                # pris langt over alt, hvad oellen koster nogen steder.
                _ceiling = 0
                for _p in b.get("prices", []):
                    _ceiling = max(
                        _ceiling,
                        _p.get("price_dkk") or _p.get("price") or 0,
                        _p.get("old_price") or 0,
                    )
                if _change >= 0:
                    _plausible = True
                else:
                    _pct = abs(_change) / _ref_price if _ref_price > 0 else 0
                    # Frasortér kun naar BEGGE alarmklokker ringer:
                    # faldet er ekstremt (>60%) OG referenceprisen har
                    # ingen stoette i nutidens priser (old_price eller
                    # andre butikker). Store men bekraeftede udloebs-
                    # rabatter (80%+) passerer via loftet; moderate fald
                    # (<=60%) passerer altid.
                    _plausible = _pct <= 0.60 or (_ceiling > 0 and _ref_price <= _ceiling * 1.3)
                if _plausible:
                    b["price_change_7d"] = _change
                else:
                    _implausible_drops.append((slug, _ref_price, _recent[-1][1]))

    with open("price_history.json", "w", encoding="utf-8") as f:
        json.dump(history_out, f, ensure_ascii=False)

    print(f"   {len(history_out)} øl fik en prishistorik-graf (ud af {len(beer_list)} i alt)")
    if _implausible_drops:
        print(f"   ⚠️ {len(_implausible_drops)} usandsynlige prisfald frasorteret (>60% fald uden stoette i nutidens priser — sandsynligvis falske matches):")
        for _slug, _old_p, _new_p in _implausible_drops[:10]:
            print(f"      {_old_p:8.2f} → {_new_p:8.2f} kr   {_slug}")
        if len(_implausible_drops) > 10:
            print(f"      ... og {len(_implausible_drops) - 10} flere")


import re as _navne_re

_MOJIBAKE_MARKERS = ("\u00c2", "\u00c3", "\u00e2\u20ac")

# Kendte mojibake-sekvenser -> korrekt tegn. Bruges naar fuld
# re-dekodning ikke er mulig, fordi strengen OGSAA indeholder aegte
# non-ASCII (fx 'Ängla-Pils Â· ...'). Laengste sekvenser foerst.
_MOJIBAKE_MAP = (
    ("\u00e2\u20ac\u201c", "\u2013"),
    ("\u00e2\u20ac\u2122", "\u2019"),
    ("\u00c3\u00a6", "\u00e6"),
    ("\u00c3\u00b8", "\u00f8"),
    ("\u00c3\u00a5", "\u00e5"),
    ("\u00c3\u00a9", "\u00e9"),
    ("\u00c3\u00bc", "\u00fc"),
    ("\u00c3\u00a4", "\u00e4"),
    ("\u00c3\u00b6", "\u00f6"),
    ("\u00c2\u00b7", "\u00b7"),
    ("\u00c2\u00a0", " "),
)

def _fix_mojibake(s):
    """Reparer UTF-8-tekst fejllaest som Latin-1 ('Â·' -> '·').
    Foerst forsoeges fuld re-dekodning (bedst naar hele strengen er
    mojibake). Fejler den — eller hjaelper den ikke — rettes kendte
    sekvenser punktvis via _MOJIBAKE_MAP."""
    if not s or not any(m in s for m in _MOJIBAKE_MARKERS):
        return s
    try:
        repaired = s.encode("latin-1").decode("utf-8")
        before = sum(s.count(m) for m in _MOJIBAKE_MARKERS)
        after = sum(repaired.count(m) for m in _MOJIBAKE_MARKERS)
        if after < before:
            return repaired
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    for _bad, _good in _MOJIBAKE_MAP:
        s = s.replace(_bad, _good)
    return s

_BEST_FOER_RE = _navne_re.compile(
    r"\s*[\u2013\-\u2014]?\s*(BEDST\s*F\u00d8R|BEST\s*BEFORE)\s*:?\s*"
    r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s*",
    _navne_re.IGNORECASE,
)
_DUP_PAK_RE = _navne_re.compile(r"(\(\d+\s*stk\.?\))(\s*\1)+", _navne_re.IGNORECASE)

def sanitize_item_names(item):
    """Renser navne-stoej fra kilderne: mojibake, BEDST FOER-datoer og
    dublerede pak-angivelser. Facit anvendes EFTER og vinder stadig."""
    name = item.get("name")
    if name:
        name = _fix_mojibake(name)
        name = _BEST_FOER_RE.sub(" ", name)
        name = _DUP_PAK_RE.sub(r"\1", name)
        name = _navne_re.sub(r"\s{2,}", " ", name).strip(" -\u2013\u2014,")
        item["name"] = name
    for _f in ("brewery", "description", "type"):
        _v = item.get(_f)
        if _v:
            _v = _fix_mojibake(_v)
            if _f == "description":
                _v = _BEST_FOER_RE.sub(" ", _v)
                _v = _navne_re.sub(r"\s{2,}", " ", _v).strip()
            item[_f] = _v


def main():
    start_time = time.time()
    print("=" * 60)
    print(f"🍺 BeerSniffer — Daglig opdatering")
    print(f"   Tidspunkt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. Kør alle scrapers
    items, results = run_all_scrapers()

    print(f"\n📊 Scraping resultat:")
    for shop, count in results.items():
        print(f"   {shop}: {count}")
    print(f"   TOTAL: {len(items)} produkter")

    if not items:
        print("\n❌ Ingen items hentet — afbryder")
        return

    # 1a2. Rens navne-stoej fra kilderne (mojibake, BEDST FOER-datoer,
    #       dublerede pak-angivelser) — facit anvendes efter og vinder.
    _renset = 0
    for _it in items:
        _foer = _it.get("name")
        sanitize_item_names(_it)
        if _it.get("name") != _foer:
            _renset += 1
    if _renset:
        print(f"   \U0001F9F9 {_renset} navne renset for kilde-stoej")

    # 1b. Facitliste: anvend manuelle overrides FOER matchning (facit vinder)
    print(f"\n\U0001F4D8 Anvender facitliste (fejlliste.xlsx)...")
    _facit = load_fejlliste("fejlliste.xlsx")
    for _it in items:
        apply_overrides(_it, _facit)
    print(f"   {len(_facit)} kendte rettelser i facit")

    # 2. Gem i Supabase (bevarer historik)
    print(f"\n💾 Gemmer i Supabase...")
    db = SessionLocal()
    try:
        ingest_batch(db, items)
    finally:
        pass  # holder db åben til næste step

    # 3. Byg grupperet liste fra database
    print(f"\n🔗 Bygger grupperet ølliste...")
    beer_list = build_beer_list_from_db(db)

    print(f"\n📈 Bygger prishistorik...")
    build_price_history(db, beer_list)
    db.close()

    # Rens navne-stoej OGSAA paa output-siden: navnene her kommer fra
    # databasen, hvor oel fra tidligere ingests stadig kan baere
    # mojibake/BEDST FOER/dublerede pak-angivelser. (Input-rensningen
    # i trin 1a2 forhindrer kun NY forurening.)
    _renset_out = 0
    for _b in beer_list:
        _foer = _b.get("name")
        sanitize_item_names(_b)
        if _b.get("name") != _foer:
            _renset_out += 1
    if _renset_out:
        print(f"   \U0001F9F9 {_renset_out} navne renset i output (gamle DB-navne)")

    # Fjern interne id-lister — de skal ikke med i data.json
    for _b in beer_list:
        _b.pop("_all_ids", None)

    # 4. Beregn stats
    total_beers = len(beer_list)
    deals_count = sum(1 for b in beer_list if b["max_discount_pct"] > 0)
    shop_names = sorted(set(
        p["shop_name"]
        for b in beer_list
        for p in b["prices"]
    ))
    types = sorted(set(b["type"] for b in beer_list if b.get("type")))
    cheapest = min((b["cheapest_price"] for b in beer_list), default=0)

    # 5. Saml data.json
    output = {
        "updated_at": datetime.now().isoformat(),
        "stats": {
            "total": total_beers,
            "deals": deals_count,
            "shops": len(shop_names),
            "shop_names": shop_names,
            "types": types,
            "cheapest": round(cheapest, 0),
        },
        "beers": beer_list,
    }

    # 6. Skriv til data.json
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # 7. Generér individuelle øl-sider og sitemap ud fra det nye data.json
    print(f"\n🌐 Genererer øl-sider og sitemap...")
    try:
        subprocess.run([sys.executable, "generate_beer_pages.py", "--all"], check=True)
        subprocess.run([sys.executable, "generate_sitemap.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Fejl under generering af øl-sider/sitemap: {e}")
        print("   data.json er stadig skrevet korrekt — kør generatorerne manuelt for at se fejlen.")

    # 8. Opdater facitliste (bevarer dine rettelser, flagger nye huller)
    _stats = write_fejlliste(items, _facit, "fejlliste.xlsx")
    print(f"\U0001F4DD fejlliste.xlsx opdateret: {_stats['rows']} raekker, {_stats['mangler']} mangler")

    # 9. Stempl DATA_VERSION i index.html — så CDN-cachen invalideres
    #    præcis når (og kun når) der er ny data.
    try:
        subprocess.run([sys.executable, "stamp_data_version.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Kunne ikke stemple DATA_VERSION i index.html: {e}")
        print("   Kør 'python stamp_data_version.py' manuelt, ellers ser besøgende gammel data fra cache.")

    file_size = round(time.time() - start_time, 1)
    print(f"\n✅ FÆRDIG på {file_size}s")
    print(f"   Skrev data.json med {total_beers} unikke øl fra {len(shop_names)} butikker")
    print(f"   Aktive tilbud: {deals_count}")
    print(f"   Billigste øl: {round(cheapest, 2)} kr")
    print(f"\n📤 Næste skridt:")
    print(f"   git add data.json ol/ sitemap.xml index.html")
    print(f"   git commit -m \"Daglig opdatering {datetime.now().strftime('%Y-%m-%d')}\"")
    print(f"   git push")


if __name__ == "__main__":
    main()