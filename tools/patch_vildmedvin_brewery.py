"""
Patch: Vild med Vin brewery-fallback.

Naar g:brand-feltet er tomt (ca. 85 oel), proever vi at udlede bryggeriet
fra titlen: teksten foer foerste komma eller ' - '.

Sikkerhed:
  - Roerer KUN items hvor g:brand allerede er None (de 88% med brand er uroert).
  - Springer pakker/smagekasser over (de har ikke ET bryggeri).
  - Afviser for korte eller generiske kandidater.
  - Facit-laget koerer EFTER og vinder, saa et forkert gaet kan altid
    rettes manuelt i fejlliste.xlsx.

Koeres fra repo-roden:  python patch_vildmedvin_brewery.py
"""
import shutil
import sys
import os

PATH = "app/scrapers/vildmedvin.py"

# Hjaelpefunktion der indsaettes i toppen af filen (efter importerne)
HELPER = '''

# --- Brewery-fallback: udled bryggeri fra titel naar g:brand er tom ---
_BREWERY_SKIP_WORDS = {
    "oel", "\u00f8l", "oelpakke", "\u00f8lpakke", "pakke", "smagekasse",
    "smagess\u00e6t", "blandet", "mix", "gavekurv", "gave", "kasse",
}

def _brewery_from_title(title):
    """Returner sandsynligt bryggeri fra titel, ellers None.
    Tager teksten foer foerste ',' eller ' - '. Konservativt."""
    if not title:
        return None
    t = title.strip()
    low = t.lower()
    # spring pakker/blandinger over - de har ikke ET bryggeri
    if any(w in low for w in ["pakke", "smagekasse", "smagess", "blandet", "bland selv", "gavekurv"]):
        return None
    # find foerste separator: komma vinder over ' - ' hvis den kommer foerst
    cut = len(t)
    ci = t.find(",")
    if ci != -1:
        cut = min(cut, ci)
    di = t.find(" - ")
    if di != -1:
        cut = min(cut, di)
    if cut == len(t):
        return None  # ingen separator -> for usikkert
    cand = t[:cut].strip()
    # afvis for korte / generiske kandidater
    if len(cand) < 3:
        return None
    if cand.lower() in _BREWERY_SKIP_WORDS:
        return None
    # afvis hvis kandidaten ligner en stilart frem for et bryggeri (valgfrit, let)
    return cand
'''

OLD = '        # Bryggeri \u2014 direkte fra g:brand\n        brewery = item.findtext("g:brand", default="", namespaces=NS).strip() or None\n'
# Bemaerk: tankestregen i kommentaren kan vaere mojibake i filen; vi ankrer derfor
# paa selve kode-linjen i stedet, som er stabil.

ANCHOR = 'brewery = item.findtext("g:brand", default="", namespaces=NS).strip() or None'
NEW_LINE = ('brewery = item.findtext("g:brand", default="", namespaces=NS).strip() or None\n'
            '        if brewery is None:\n'
            '            brewery = _brewery_from_title(title)')


def main():
    if not os.path.exists(PATH):
        print(f"FEJL: finder ikke {PATH}")
        return

    with open(PATH, "r", encoding="utf-8") as f:
        src = f.read()

    if "_brewery_from_title" in src:
        print("SKIP: ser allerede patchet ud (_brewery_from_title findes).")
        return

    if ANCHOR not in src:
        print("FEJL: fandt ikke g:brand-linjen. Ingen aendringer.")
        return
    if src.count(ANCHOR) != 1:
        print(f"ADVARSEL: g:brand-linjen findes {src.count(ANCHOR)} gange. Stopper.")
        return

    shutil.copy(PATH, PATH + ".bak")
    print(f"Backup: {PATH}.bak")

    # 1) indsaet helper efter detect_type-importen (stabilt anker)
    imp_anchor = "from app.utils.detect_type import detect_type\n"
    if imp_anchor not in src:
        print("FEJL: fandt ikke detect_type-import som anker for helper.")
        return
    src = src.replace(imp_anchor, imp_anchor + HELPER, 1)

    # 2) tilfoej fallback-kald lige efter g:brand-linjen
    src = src.replace(ANCHOR, NEW_LINE, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("OK: titel-fallback tilfoejet. g:brand bruges stadig foerst.")


if __name__ == "__main__":
    main()