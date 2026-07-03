# -*- coding: utf-8 -*-
"""
diag_dubletter_live.py — READ-ONLY.

Skiller de LEVENDE dubletter fra de DOEDE rester.

Et '-2'-slug er kun et SYNLIGT problem, hvis BAADE base-raekken og
'-2'-raekken har priser lige nu (begge er saa i data.json og vises
dobbelt for brugeren). Raekker uden priser springes over i buildet og
er usynlige — de er blot DB-skrald fra gamle ingests.

Dette script:
  1. Optaeller alle '-2'-raekker i DB og hvor mange der er doede (0 priser).
  2. Viser KUN de live-mod-live-par (aegte synlige dubletter) og hvilken
     gate der blokerer deres sammensmeltning.

Ingen skrivning. Ingen sletning. Kun SELECT + db.close().
Koer fra roden med .venv aktiv:
    python diag_dubletter_live.py
"""

import sys
from collections import defaultdict
from html import unescape

try:
    from sqlalchemy.orm import joinedload
    from app.database import SessionLocal
    from app.models import Beer
    from app.services.matching import (
        normalize_for_matching, style_fingerprint, styles_compatible,
        volumes_compatible, abv_compatible, breweries_compatible,
        variants_compatible, similarity_score, has_meaningful_overlap,
        required_threshold,
    )
except Exception as e:
    print(f"❌ Kunne ikke importere app-moduler: {e}")
    print("   Koer fra roden af projektet med .venv aktiv.")
    sys.exit(1)


def npr(b):
    return len(b.prices or [])


def gate_report(A, B):
    fpA, fpB = style_fingerprint(A.name), style_fingerprint(B.name)
    if not styles_compatible(fpB, fpA):
        return "styles", f"{sorted(fpB)} vs {sorted(fpA)}"
    if not volumes_compatible(B.volume_cl, A.volume_cl):
        return "volume", f"{B.volume_cl} vs {A.volume_cl}"
    if not abv_compatible(B.abv, A.abv):
        return "abv", f"{B.abv} vs {A.abv}"
    if not breweries_compatible(B.brewery, A.brewery, B.name, A.name):
        return "brewery", f"{B.brewery!r} vs {A.brewery!r}"
    if not variants_compatible(B.name, A.name):
        return "variants", "forskellige variant-markoerer"
    if not has_meaningful_overlap(B.name, A.name):
        return "overlap", "ingen faelles meningsfulde ord"
    score = similarity_score(
        normalize_for_matching(B.name), normalize_for_matching(A.name),
        B.abv, A.abv, B.brewery, A.brewery, fpB, fpA,
    )
    thr = required_threshold(B.abv, A.abv, B.volume_cl, A.volume_cl, B.brewery, A.brewery)
    if score < thr:
        return "score", f"score {score:.1f} < threshold {thr:.1f}"
    return "INGEN BLOCKER", f"score {score:.1f} >= {thr:.1f}"


def main():
    db = SessionLocal()
    try:
        beers = db.query(Beer).options(joinedload(Beer.prices)).all()
    finally:
        db.close()

    by_slug = defaultdict(list)
    for b in beers:
        if b.slug:
            by_slug[b.slug].append(b)

    two_rows = [b for s in by_slug for b in by_slug[s] if s.endswith("-2")]
    dead = sum(1 for b in two_rows if npr(b) == 0)
    live = len(two_rows) - dead

    print(f"'-2'-raekker i databasen:  {len(two_rows)}")
    print(f"   doede (0 priser, usynlige paa sitet): {dead}")
    print(f"   live  (>0 priser):                     {live}\n")

    visible = []      # base live + '-2' live  => aegte synlig dublet
    solo_live = []    # '-2' live, men base doed/fraovaerende => harmloes
    for slug, rows in by_slug.items():
        if not slug.endswith("-2"):
            continue
        two = max(rows, key=npr)
        if npr(two) == 0:
            continue
        base_rows = by_slug.get(slug[:-2])
        base_live = [r for r in (base_rows or []) if npr(r) > 0]
        if base_live:
            one = max(base_live, key=npr)
            visible.append((slug[:-2], one, two))
        else:
            solo_live.append((slug, two))

    print("=" * 72)
    print(f"SYNLIGE DUBLETTER (begge har priser) — {len(visible)} par")
    print("=" * 72)
    grupper = defaultdict(list)
    for base, A, B in visible:
        blocker, detail = gate_report(A, B)
        grupper[blocker].append((base, A, B, detail))

    for blocker in ["abv", "brewery", "volume", "variants", "styles",
                    "overlap", "score", "INGEN BLOCKER"]:
        items = grupper.get(blocker)
        if not items:
            continue
        print(f"\n--- BLOKERET PAA: {blocker}  ({len(items)}) ---")
        for base, A, B, detail in items:
            print(f"  {base}")
            print(f"     A: {unescape(A.name)!r}  [vol={A.volume_cl} abv={A.abv} "
                  f"brew={A.brewery!r} priser={npr(A)}]")
            print(f"     B: {unescape(B.name)!r}  [vol={B.volume_cl} abv={B.abv} "
                  f"brew={B.brewery!r} priser={npr(B)}]")
            print(f"     -> {detail}")

    print("\n" + "=" * 72)
    print(f"LIVE '-2' MED DOED/INGEN BASE (harmloes, beholdes) — {len(solo_live)} stk")
    print("=" * 72)
    for slug, B in solo_live:
        print(f"   {slug:60s} {unescape(B.name)}  [priser={npr(B)}]")


if __name__ == "__main__":
    main()