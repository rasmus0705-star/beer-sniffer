"""
patch_ingest_add_slug.py

Sørger for at NYE øl automatisk får en slug tildelt, når de oprettes i
ingest.py fremover. Rører IKKE eksisterende øl (de har allerede fået deres
slug via backfill_slugs.py).

Kør fra roden af dit projekt:
    python patch_ingest_add_slug.py
"""

import shutil
import sys
from pathlib import Path

TARGET = Path("app/services/ingest.py")

if not TARGET.exists():
    print(f"FEJL: Finder ikke {TARGET.resolve()} — tjek stien til ingest.py")
    sys.exit(1)

backup = TARGET.with_suffix(".py.bak")
shutil.copy(TARGET, backup)
print(f"Backup gemt som: {backup}")

text = TARGET.read_text(encoding="utf-8")


def apply(old, new, label):
    global text
    count = text.count(old)
    if count == 0:
        print(f"  [SPRINGET OVER] Fandt ikke tekst til: {label} — tjek ingest.py manuelt.")
        return False
    if count > 1:
        print(f"  [ADVARSEL] Teksten til '{label}' findes {count} gange — springer over.")
        return False
    text = text.replace(old, new)
    print(f"  [OK] {label}")
    return True


# 1) Import
apply(
    """from app.services.matching import (
    normalize_for_matching,""",
    """from app.utils.slugify import slugify, resolve_collisions
from app.services.matching import (
    normalize_for_matching,""",
    "Import af slugify + resolve_collisions",
)

# 2) Byg eksisterende-slugs-sæt ved start af ingest_batch
apply(
    """    all_beers = db.query(Beer).all()

    beers_by_volume = {}
    beers_with_no_volume = []""",
    """    all_beers = db.query(Beer).all()

    existing_slugs = {b.slug for b in all_beers if b.slug}

    beers_by_volume = {}
    beers_with_no_volume = []""",
    "Opbyg eksisterende-slugs-sæt",
)

# 3) Tildel slug ved oprettelse af ny Beer-række
apply(
    """        if not beer:
            beer = Beer(
                name=item_name,
                normalized_name=normalize_name(item_name),
                brewery=item_brewery,
                type=item.get("type"),
                volume_cl=item_vol,
                abv=item_abv,
                image=item.get("image"),
            )
            db.add(beer)
            db.flush()""",
    """        if not beer:
            new_slug = slugify(item_name, item_brewery)
            new_slug = resolve_collisions(new_slug, existing_slugs)
            existing_slugs.add(new_slug)

            beer = Beer(
                name=item_name,
                normalized_name=normalize_name(item_name),
                brewery=item_brewery,
                type=item.get("type"),
                volume_cl=item_vol,
                abv=item_abv,
                image=item.get("image"),
                slug=new_slug,
            )
            db.add(beer)
            db.flush()""",
    "Tildel slug ved ny Beer-oprettelse",
)

TARGET.write_text(text, encoding="utf-8")
print(f"\nFærdig! {TARGET} er opdateret.")
print("Test isoleret næste gang du kører build_data.py eller en enkelt scraper,")
print("og tjek at nye øl (hvis der er nogen) får en slug i databasen.")