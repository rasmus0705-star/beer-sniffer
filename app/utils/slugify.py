"""
app/utils/slugify.py — Genererer stabile, pæne URL-slugs fra beskidte ølnavne.

VIGTIGT: Dette script er ISOLERET til test. Det rører hverken database eller
build_data.py. Formålet er at se resultatet på rigtige data, før vi kobler
det til noget som helst.

Bruger samme accent-stripping som app/services/matching.py for konsistens,
men er IKKE beregnet til matching — kun til at generere den tekst der vises
i URL'en.
"""
import re


def strip_accents(s: str) -> str:
    """Udvidet udgave af matching.py's version — tilføjet islandsk/færøske
    bogstaver (ó, í, ú, ý, ð, þ) samt ñ/ç, da de forekommer i rigtig data
    (fx færøske bryggerier som Föroya Bjór). Holdt i sync bevidst, ikke
    importeret, for at denne fil kan testes 100% isoleret."""
    return (s.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
             .replace("Æ", "ae").replace("Ø", "oe").replace("Å", "aa")
             .replace("é", "e").replace("è", "e").replace("ê", "e").replace("ë", "e")
             .replace("á", "a").replace("à", "a").replace("â", "a")
             .replace("ó", "o").replace("ò", "o").replace("ô", "o")
             .replace("í", "i").replace("ì", "i").replace("î", "i")
             .replace("ú", "u").replace("ù", "u").replace("û", "u")
             .replace("ý", "y").replace("ð", "d").replace("þ", "th")
             .replace("ñ", "n").replace("ç", "c")
             .replace("ü", "u").replace("ö", "o").replace("ä", "a"))


# ── Kendt navne-støj, fjernes FØR alt andet ──────────────────────────

# "- BEDST FØR: 03.03.2026" / "(BEDST FØR: 03.03.2026)" (case-insensitive)
_RE_BEDST_FOER = re.compile(
    r"[\-\(]?\s*bedst\s*f[øo]r:?\s*\d{1,2}[./]\d{1,2}[./]\d{2,4}\s*\)?",
    re.IGNORECASE,
)

# "(Best By: June 2026)" / "Best By: 30/07-2026" — engelsk variant
_RE_BEST_BY = re.compile(
    r"\(?\s*best\s*by:?\s*[a-z0-9/\-\s]{4,20}\)?",
    re.IGNORECASE,
)

# "Best before: 31/08-2026" — bruges bl.a. fejlagtigt i brewery-feltet
_RE_BEST_BEFORE = re.compile(
    r"\(?\s*best\s*before:?\s*[a-z0-9/\-\s]{4,20}\)?",
    re.IGNORECASE,
)

# Trailing " - Øl" (Vild med Vin's navnekonvention)
_RE_TRAILING_OEL = re.compile(r"\s*-\s*[øo]l\s*$", re.IGNORECASE)

# Mojibake fra dobbelt-UTF8-encoding, set i rigtig data ("Ängla-Pils Â· ...")
_MOJIBAKE_FIXES = {
    "Â·": "-",
    "â€“": "-",
    "â€™": "'",
}

# Dubleret parentes-info, fx "(24 stk.) (24 stk.)" -> "(24 stk.)"
_RE_DUPLICATE_PAREN = re.compile(r"(\([^)]*\))\s*\1")

# Volumen ("33 cl.", "0,5 l") og procent ("5,0%", "0,0%") — ren tal-støj i URL'er
_RE_VOLUME = re.compile(r"\d+[.,]?\d*\s?(cl|ml|l|liter)\b\.?", re.IGNORECASE)
_RE_PERCENT = re.compile(r"\d+[.,]?\d*\s?%")


# Sikkerhedsnet: hvis 'brewery'-feltet fejlagtigt indeholder shop-navnet
# (set i rigtig data, fx Beershoppen-scraperen), skal det ALDRIG prependes
# til en slug. Holdt i sync med jeres SHOPPING/shop_names liste.
_KNOWN_SHOP_NAMES = {
    "a good case", "beer me", "beermatch", "beershoppen", "best of beers",
    "brygshoppen", "drikbeer", "vild med vin", "oeltanken", "øltanken",
}


def _word_overlap_ratio(a: str, b: str) -> float:
    """Simpel, afhængighedsfri fuzzy-check: hvor stor en andel af b's ord
    findes i a. Bruges til at undgå at prepende bryggeri, når det reelt
    allerede er en del af navnet — også ved stave-/encodingforskelle
    (fx 'Föroya' vs 'Føroya')."""
    words_a = set(strip_accents(a.lower()).split())
    words_b = set(strip_accents(b.lower()).split())
    if not words_b:
        return 0.0
    matched = 0
    for wb in words_b:
        if wb in words_a:
            matched += 1
            continue
        # tolerer 1-2 tegns forskel (encoding-varianter af samme ord)
        for wa in words_a:
            if abs(len(wa) - len(wb)) <= 1 and sum(c1 != c2 for c1, c2 in zip(wa, wb)) <= 2:
                matched += 1
                break
    return matched / len(words_b)


def clean_name(raw_name: str) -> str:
    """Fjerner kendt støj fra et råt ølnavn FØR slug-generering.
    Bevarer stadig menneskelæselig tekst — bruges kun internt af slugify()."""
    if not raw_name:
        return ""

    s = raw_name
    for bad, good in _MOJIBAKE_FIXES.items():
        s = s.replace(bad, good)

    s = _RE_DUPLICATE_PAREN.sub(r"\1", s)
    s = _RE_BEDST_FOER.sub(" ", s)
    s = _RE_BEST_BY.sub(" ", s)
    s = _RE_BEST_BEFORE.sub(" ", s)
    s = _RE_TRAILING_OEL.sub("", s)
    s = _RE_VOLUME.sub(" ", s)
    s = _RE_PERCENT.sub(" ", s)

    s = re.sub(r"\s+", " ", s).strip()
    return s


def slugify(raw_name: str, brewery: str = None, max_words: int = 8) -> str:
    """
    Laver en pæn, stabil URL-slug fra et ølnavn.
    - Renser kendt navne-støj (datoer, dobbelt-parenteser, mojibake)
    - Sætter bryggeri foran hvis det ikke allerede er en del af navnet
    - Begrænser til max_words ord for at holde URL'en kort og læsbar
    """
    cleaned = clean_name(raw_name)

    combined = cleaned
    if brewery:
        brewery_clean = clean_name(brewery)
        is_fake_brewery = (
            not brewery_clean
            or re.search(r"\d{2,4}", brewery_clean)
            or strip_accents(brewery_clean.lower()) in _KNOWN_SHOP_NAMES
        )
        if not is_fake_brewery:
            # Fuzzy overlap i stedet for eksakt substring — håndterer
            # encoding-varianter som 'Föroya' (brewery) vs 'Føroya' (navn)
            if _word_overlap_ratio(cleaned, brewery_clean) < 0.5:
                combined = f"{brewery_clean} {cleaned}"

    s = strip_accents(combined.lower())
    s = s.replace("'", "").replace("’", "").replace("‘", "")
    s = re.sub(r"[^a-z0-9\s-]", " ", s)
    s = re.sub(r"[\s-]+", " ", s).strip()

    words = s.split(" ")[:max_words]
    slug = "-".join(w for w in words if w)

    return slug or "oel"


def resolve_collisions(slug: str, existing_slugs: set) -> str:
    """Hvis slug allerede findes, tilføj -2, -3, osv."""
    if slug not in existing_slugs:
        return slug
    n = 2
    while f"{slug}-{n}" in existing_slugs:
        n += 1
    return f"{slug}-{n}"


# ── TEST mod rigtige eksempler fra jeres data.json ──────────────────
if __name__ == "__main__":
    test_cases = [
        ("Lervig, Magic Clouds - BEDST FØR: 03.03.2026 - Øl", "Lervig"),
        ("Hancock, Høkerbajer - Øl", "Hancock"),
        ("Wild Horse Brewing Co. - Tonnau (Siren Collab) (Best By: June 2026)", "Wild Horse Brewing Co."),
        ("Föroya Bjór, Classic Dark Lager - BEDST FØR: 17.08.2026 - Øl", "Føroya Bjór"),
        ("Hancock 150-års jubilæums Øl - Øl", "Hancock"),
        ("150 års jubilæum - Hancock  - 33 cl. - 5,0%", "Beershoppen"),
        ("Ängla-Pils Â· Glutenfri Pilsner fra Spike Brewery", "Spike Brewery"),
        ("Thisted Bryghus, ØKO Thy Pilsner 33 cl. - Øl", "Thisted Bryghus"),
        ("Estrella Galicia Alkoholfri - Øl", "Estrella Galicia"),
        ("Tyskie Gronie – 5,2% Lager (24 stk.) (24 stk.)", "Tyskie"),
        ("Estrella - Estrella Galicia 0,0 Tostada - 0% Alkoholfri Lager", "Best before: 31/08-2026"),
        ("Dos Equis - Chelada Lime & Salt - 4,2% Mexican Lager (24 stk.)", "Best Before: 30/07-2026"),
        ("Brasserie D'achouffe, La Chouffe Alkoholfri - Øl", "Brasserie D'achouffe"),
    ]

    seen = set()
    print(f"{'RÅT NAVN':<75} -> SLUG")
    print("-" * 110)
    for name, brewery in test_cases:
        slug = slugify(name, brewery)
        slug = resolve_collisions(slug, seen)
        seen.add(slug)
        print(f"{name:<75} -> {slug}")