"""
backfill_slugs.py — Étgangs-script der tildeler slugs til alle eksisterende
Beer-rækker i Supabase, der endnu ikke har én.

SIKKERHED:
- Kører som DRY-RUN som standard (viser hvad den ville gøre, skriver intet)
- Kræver eksplicit --apply for reelt at gemme ændringer i databasen
- Rører KUN rækker hvor slug er NULL — allerede tildelte slugs ændres aldrig
- Behandler i id-rækkefølge (stigende) for deterministisk, forudsigelig adfærd

Kør fra roden af dit projekt:
    python backfill_slugs.py              # dry-run, viser resultat
    python backfill_slugs.py --apply      # skriver rigtigt til databasen

Forudsætninger:
1. SQL-ændringen er kørt i Supabase (ALTER TABLE beers ADD COLUMN slug ...)
2. app/models.py har fået 'slug'-feltet (patch_add_slug_field.py)
3. app/utils/slugify.py findes (Trin 2-filen)
"""

import sys
from dotenv import load_dotenv

load_dotenv()

from app.database import SessionLocal
from app.models import Beer
from app.utils.slugify import slugify, resolve_collisions


def main():
    apply = "--apply" in sys.argv

    db = SessionLocal()
    try:
        all_beers = db.query(Beer).order_by(Beer.id.asc()).all()
        print(f"Fandt {len(all_beers)} øl i databasen totalt.")

        existing_slugs = {b.slug for b in all_beers if b.slug}
        print(f"{len(existing_slugs)} har allerede en slug (røres ikke).")

        to_process = [b for b in all_beers if not b.slug]
        print(f"{len(to_process)} mangler en slug og vil blive behandlet.\n")

        if not to_process:
            print("Intet at gøre — alle øl har allerede en slug.")
            return

        collisions_resolved = 0
        samples = []

        for beer in to_process:
            slug = slugify(beer.name, beer.brewery)
            final_slug = resolve_collisions(slug, existing_slugs)
            if final_slug != slug:
                collisions_resolved += 1
            existing_slugs.add(final_slug)

            if apply:
                beer.slug = final_slug
            else:
                samples.append((beer.id, beer.name, final_slug))

        if apply:
            db.commit()
            print(f"✅ FÆRDIG — {len(to_process)} øl fik en slug, {collisions_resolved} kollisioner løst.")
            print("Ændringerne er gemt i databasen.")
        else:
            print("── DRY-RUN — intet er gemt endnu ──\n")
            print(f"{'ID':<8}{'NAVN':<70}SLUG")
            print("-" * 130)
            for beer_id, name, slug in samples[:30]:
                name_short = (name[:67] + "...") if len(name) > 70 else name
                print(f"{beer_id:<8}{name_short:<70}{slug}")
            if len(samples) > 30:
                print(f"... og {len(samples) - 30} flere (kun de første 30 vist)")
            print(f"\nI alt: {len(to_process)} øl ville få en slug, {collisions_resolved} kollisioner ville blive løst.")
            print("\nKør med --apply for reelt at gemme disse slugs i databasen:")
            print("    python backfill_slugs.py --apply")

    finally:
        db.close()


if __name__ == "__main__":
    main()