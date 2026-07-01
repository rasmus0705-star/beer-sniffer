"""
patch_slugify_apostrophes.py

Retter apostrof-håndtering i app/utils/slugify.py, SÅ:
  "Dead Man's Hand"        -> dead-mans-hand    (i stedet for dead-man-s-hand)
  "Brasserie D'achouffe"   -> brasserie-dachouffe (i stedet for brasserie-d-achouffe)

VIGTIGT: Kør dette FØR du kører backfill_slugs.py --apply, ellers sidder
den akavede version fast permanent på alle apostrof-øl.

Kør fra projekt-roden:
    python patch_slugify_apostrophes.py
"""

import shutil
import sys
from pathlib import Path

TARGET = Path("app/utils/slugify.py")

if not TARGET.exists():
    print(f"FEJL: Finder ikke {TARGET.resolve()} — tjek at slugify.py ligger i app/utils/")
    sys.exit(1)

backup = TARGET.with_suffix(".py.bak")
shutil.copy(TARGET, backup)
print(f"Backup gemt som: {backup}")

text = TARGET.read_text(encoding="utf-8")

old = """    s = strip_accents(combined.lower())
    s = re.sub(r"[^a-z0-9\\s-]", " ", s)
    s = re.sub(r"[\\s-]+", " ", s).strip()"""

new = """    s = strip_accents(combined.lower())
    s = s.replace("'", "").replace("\u2019", "").replace("\u2018", "")
    s = re.sub(r"[^a-z0-9\\s-]", " ", s)
    s = re.sub(r"[\\s-]+", " ", s).strip()"""

if old not in text:
    print("[SPRINGET OVER] Fandt ikke det forventede mønster — tjek app/utils/slugify.py manuelt.")
    sys.exit(1)

text = text.replace(old, new)
TARGET.write_text(text, encoding="utf-8")
print("[OK] Apostrof-håndtering rettet i app/utils/slugify.py")
print("\nKør nu igen (dry-run) for at bekræfte:")
print("    python backfill_slugs.py")