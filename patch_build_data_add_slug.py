"""
patch_build_data_add_slug.py

Sørger for at data.json indeholder et 'slug'-felt pr. øl, valgt DETERMINISTISK
fra den Beer-række med LAVEST id i gruppen — uanset i hvilken rækkefølge
grupperingen sker denne kørsel.

Kør fra roden af dit projekt:
    python patch_build_data_add_slug.py
"""

import shutil
import sys
from pathlib import Path

TARGET = Path("build_data.py")

if not TARGET.exists():
    print(f"FEJL: Finder ikke {TARGET.resolve()} — kør scriptet fra din projekt-rod")
    sys.exit(1)

backup = TARGET.with_suffix(".py.bak")
shutil.copy(TARGET, backup)
print(f"Backup gemt som: {backup}")

text = TARGET.read_text(encoding="utf-8")


def apply(old, new, label):
    global text
    count = text.count(old)
    if count == 0:
        print(f"  [SPRINGET OVER] Fandt ikke tekst til: {label} — tjek build_data.py manuelt.")
        return False
    if count > 1:
        print(f"  [ADVARSEL] Teksten til '{label}' findes {count} gange — springer over.")
        return False
    text = text.replace(old, new)
    print(f"  [OK] {label}")
    return True


# 1) Ved ny gruppe: gem slug sammen med id (den første Beer i gruppen)
apply(
    """            counter += 1
            key = f"g_{counter}"
            grouped[key] = {
                "id": beer.id,
                "name": beer.name,""",
    """            counter += 1
            key = f"g_{counter}"
            grouped[key] = {
                "id": beer.id,
                "slug": beer.slug,
                "name": beer.name,""",
    "Gem slug ved ny gruppe",
)

# 2) Ved match til eksisterende gruppe: opdater id+slug KUN hvis denne
#    Beer-række har lavere id end den, gruppen allerede har (deterministisk
#    valg af "ældste" række, uanset loop-rækkefølge)
apply(
    """        if best_key and best_score >= best_threshold:
            target = grouped[best_key]
            for p in beer.prices:""",
    """        if best_key and best_score >= best_threshold:
            target = grouped[best_key]
            if beer.id < target["id"]:
                target["id"] = beer.id
                target["slug"] = beer.slug
            for p in beer.prices:""",
    "Vælg laveste id/slug deterministisk ved gruppering",
)

TARGET.write_text(text, encoding="utf-8")
print(f"\nFærdig! {TARGET} er opdateret.")
print("Kør 'python build_data.py' og tjek at 'slug' optræder i data.json pr. øl.")