"""
PORT VARIANT-GATE til den LIVE matchning (build_data.py-kæden).

Den motor der faktisk kører dit site (app/services/matching.py) mangler
én ting: beskyttelse mod at en SÆRLIG version (Barrel Aged, Bourbon,
Vintage ...) matches med base-øllen. Fx blev:
    "St. Bernardus Abt 12 Barrel Aged Sour"  +  "St. Bernardus Abt 12"
slået sammen, selvom det er to vidt forskellige (og forskelligt prisede) øl.

Denne patch tilføjer:
  1. variants_compatible() i app/services/matching.py
  2. et hårdt gate-kald i build_data.py's grupperingsløkke
  3. importen i build_data.py

Kør:  python patch_variant_live.py
Backup: app/services/matching.py.bak + build_data.py.bak
"""
import io, shutil

ok = True

def patch_file(path, edits):
    """edits = liste af (old, new, navn). Gemmer kun hvis ALLE rammer."""
    global ok
    s = io.open(path, encoding="utf-8").read()
    local_ok = True
    for old, new, navn in edits:
        n = s.count(old)
        if n == 0:
            print(f"  [SPRINGER OVER] {path}: {navn} — fandt ikke teksten")
            local_ok = False
        elif n > 1:
            print(f"  [ADVARSEL] {path}: {navn} — findes {n} gange (ikke unik)")
            local_ok = False
        else:
            s = s.replace(old, new)
            print(f"  [OK] {path}: {navn}")
    if local_ok:
        shutil.copy(path, path + ".bak")
        io.open(path, "w", encoding="utf-8").write(s)
        print(f"  → gemt {path} (backup: {path}.bak)")
    else:
        ok = False
        print(f"  → IKKE gemt {path} (en patch ramte ikke)")
    return local_ok


# ── 1. matching.py: tilføj variants_compatible efter abv_compatible ───
MATCHING = "app/services/matching.py"

# Vi hænger funktionen på lige efter abv_compatible. Vi finder dens slut
# ved at indsætte før "def _norm_brewery".
variant_func = '''def _variant_markers(name):
    """
    Returnerer sættet af variant-markører i et navn. Disse signalerer en
    SÆRLIG version (fadlagret, årgang, special) — ikke bare en stilart.
    Bevidst konservativ: kun ord der reelt betyder "anden version".
    """
    if not name:
        return set()
    words = set(strip_accents(name.lower()).replace("-", " ").split())
    return words & _VARIANT_WORDS


def variants_compatible(name_a, name_b) -> bool:
    """
    Hård gate: hvis det ene navn har en variant-markør (barrel, bourbon,
    vintage ...) som det andet IKKE har, er det forskellige produkter.
    Begge skal have præcis samme sæt variant-markører for at matche.
    """
    return _variant_markers(name_a) == _variant_markers(name_b)


def _norm_brewery(b):'''

patch_matching = [
    # Konstant med variant-ord — sættes ind øverst sammen med _STOP_WORDS.
    # Vi hægter den på lige før den første 'def strip_accents'.
    (
        "def strip_accents(s: str) -> str:",
        '''_VARIANT_WORDS = {
    "barrel", "ba", "bourbon", "whisky", "whiskey", "cognac", "rum",
    "wine", "reserva", "reserve", "vintage", "anniversary", "jubilaeum",
    "jubilæum", "calvados", "tequila", "armagnac", "sherry", "port",
}


def strip_accents(s: str) -> str:''',
        "VARIANT_WORDS konstant"
    ),
    # Selve funktionen — indsættes før _norm_brewery
    (
        "def _norm_brewery(b):",
        variant_func,
        "variants_compatible funktion"
    ),
]

patch_file(MATCHING, patch_matching)

# ── 2. build_data.py: import + gate-kald ──────────────────────────────
BUILD = "build_data.py"

patch_build = [
    # Tilføj til importen fra app.services.matching
    (
        "    breweries_compatible,",
        "    breweries_compatible,\n    variants_compatible,",
        "import variants_compatible"
    ),
    # Tilføj gate i grupperingsløkken — efter breweries_compatible
    (
        """            if not breweries_compatible(brewery, g.get("brewery"), beer.name, g.get("name")):
                continue""",
        """            if not breweries_compatible(brewery, g.get("brewery"), beer.name, g.get("name")):
                continue
            if not variants_compatible(beer.name, g.get("name")):
                continue""",
        "variant-gate i grupperingsløkke"
    ),
]

patch_file(BUILD, patch_build)

# ── Resultat ──────────────────────────────────────────────────────────
if ok:
    print("\n✅ Variant-gaten er nu i den LIVE matchning.")
    print("   Kør 'python build_data.py' og tjek at St. Bernardus Abt 12")
    print("   Barrel Aged Sour står adskilt fra den almindelige Abt 12.")
else:
    print("\n⚠️  Mindst én patch ramte ikke — tjek output ovenfor.")
    print("   Filer der ikke ramte rent er IKKE gemt.")