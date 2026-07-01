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
from datetime import datetime
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
    db.close()

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

    file_size = round(time.time() - start_time, 1)
    print(f"\n✅ FÆRDIG på {file_size}s")
    print(f"   Skrev data.json med {total_beers} unikke øl fra {len(shop_names)} butikker")
    print(f"   Aktive tilbud: {deals_count}")
    print(f"   Billigste øl: {round(cheapest, 2)} kr")
    print(f"\n📤 Næste skridt:")
    print(f"   git add data.json ol/ sitemap.xml")
    print(f"   git commit -m \"Daglig opdatering {datetime.now().strftime('%Y-%m-%d')}\"")
    print(f"   git push")


if __name__ == "__main__":
    main()