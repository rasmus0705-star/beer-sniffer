"""
cleanup_bad_breweries.py — Étgangs-oprydning af eksisterende Beer-rækker,
hvor brewery-feltet er et shop-navn eller en dato i stedet for et rigtigt
bryggeri.

For hver ramt række: forsøger at udlede det rigtige bryggeri fra navnet
('Bryggeri - Produkt'-mønster). Findes intet validt, sættes brewery til
NULL i stedet for at beholde den forkerte værdi — "ukendt" er bedre end
"forkert".

SIKKERHED:
- Kører som DRY-RUN som standard
- Kræver eksplicit --apply for at skrive til databasen
- Skriver i én samlet batch (ikke én forespørgsel pr. række)

Kør fra roden af dit projekt:
    python cleanup_bad_breweries.py              # dry-run
    python cleanup_bad_breweries.py --apply       # skriver rigtigt
"""

import re
import sys
from dotenv import load_dotenv

load_dotenv()

from app.database import SessionLocal
from app.models import Beer
from app.utils.slugify import is_valid_brewery

DATE_PATTERN = re.compile(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}")


def derive_from_name(name, old_brewery=None):
    """Samme simple logik som scraperne bruger: udleder bryggeri fra
    titlen, hvis muligt. Beershoppens titler følger mønstret
    'Produkt - Bryggeri - detaljer' (modsat de fleste andre butikker),
    så for rækker der kom derfra bruges andet segment, ikke første."""
    if not name or " - " not in name:
        return None
    parts = [p.strip() for p in name.split(" - ")]

    is_from_beershoppen = old_brewery and old_brewery.strip().lower() == "beershoppen"
    if is_from_beershoppen and len(parts) >= 2:
        candidate = parts[1]
    else:
        candidate = parts[0]

    if len(candidate) > 2 and is_valid_brewery(candidate):
        return candidate
    return None


def main():
    apply = "--apply" in sys.argv

    db = SessionLocal()
    try:
        beers = db.query(Beer.id, Beer.name, Beer.brewery).filter(Beer.brewery.isnot(None)).all()

        bad = [
            (id_, name, brewery) for id_, name, brewery in beers
            if not is_valid_brewery(brewery)
        ]
        print(f"Fandt {len(bad)} øl med ugyldigt brewery-felt (ud af {len(beers)} med udfyldt brewery).")

        if not bad:
            print("Intet at rette.")
            return

        updates = []
        fixed_count = 0
        cleared_count = 0
        samples = []

        for id_, name, old_brewery in bad:
            new_brewery = derive_from_name(name, old_brewery)
            if new_brewery:
                fixed_count += 1
            else:
                cleared_count += 1
            updates.append({"id": id_, "brewery": new_brewery})
            if len(samples) < 20:
                samples.append((id_, name, old_brewery, new_brewery))

        print(f"\n{'ID':<8}{'NAVN':<55}{'FØR':<30}EFTER")
        print("-" * 130)
        for id_, name, old_b, new_b in samples:
            name_short = (name[:52] + "...") if len(name) > 55 else name
            print(f"{id_:<8}{name_short:<55}{old_b[:28]:<30}{new_b or '(ryddet)'}")
        if len(bad) > 20:
            print(f"... og {len(bad) - 20} flere")

        print(f"\nI alt: {fixed_count} ville få et rigtigt bryggeri udledt af navnet, "
              f"{cleared_count} ville blive ryddet til 'ukendt' (intet at udlede).")

        if apply:
            print(f"\nSkriver {len(updates)} opdateringer i én samlet batch...")
            db.bulk_update_mappings(Beer, updates)
            db.commit()
            print("✅ FÆRDIG — ændringerne er gemt i databasen.")
        else:
            print("\n── DRY-RUN — intet er gemt endnu ──")
            print("Kør med --apply for reelt at gemme disse ændringer:")
            print("    python cleanup_bad_breweries.py --apply")

    finally:
        db.close()


if __name__ == "__main__":
    main()