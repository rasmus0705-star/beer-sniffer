"""
patch_add_slug_field.py

Tilføjer 'slug'-feltet til Beer-modellen i app/models.py.
Kør EFTER du har kørt SQL-ændringen i Supabase (se besked fra Claude).

Kør scriptet fra roden af dit projekt (samme mappe som app/):
    python patch_add_slug_field.py
"""

import shutil
import sys
from pathlib import Path

TARGET = Path("app/models.py")

if not TARGET.exists():
    print(f"FEJL: Finder ikke {TARGET.resolve()} — kør scriptet fra din projekt-rod")
    sys.exit(1)

backup = TARGET.with_suffix(".py.bak")
shutil.copy(TARGET, backup)
print(f"Backup gemt som: {backup}")

text = TARGET.read_text(encoding="utf-8")

old = """    normalized_name = Column(String, index=True)

    brewery = Column(String)"""

new = """    normalized_name = Column(String, index=True)
    slug = Column(String, unique=True, index=True, nullable=True)

    brewery = Column(String)"""

if old not in text:
    print("[SPRINGET OVER] Fandt ikke det forventede mønster — tjek app/models.py manuelt.")
    sys.exit(1)

if text.count(old) > 1:
    print("[ADVARSEL] Mønsteret findes flere gange — springer over for sikkerheds skyld.")
    sys.exit(1)

text = text.replace(old, new)
TARGET.write_text(text, encoding="utf-8")
print(f"[OK] 'slug'-felt tilføjet til Beer-modellen i {TARGET}")