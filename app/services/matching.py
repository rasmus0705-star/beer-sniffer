"""
Fælles matching-logik for ølprodukter.
Bruges af både ingest.py (når øl gemmes) og beers.py (når øl grupperes).

VIGTIGT: ændringer her påvirker BÅDE hvordan øl gemmes OG hvordan de grupperes.
"""
import re
from rapidfuzz import fuzz
from html import unescape  # ← Ny import for HTML entity decoding


EXCLUSIVE_STYLES = [
    ("QUADRUPEL",      ["quadrupel", "quadruple", " quad "]),
    ("TRIPEL",         ["tripel", "trippel", "tripple"]),
    ("DUBBEL",         ["dubbel"]),
    ("IPA",            ["ipa", "india pale ale"]),
    ("IMPERIAL_STOUT", ["imperial stout", "russian imperial"]),
    ("STOUT",          ["stout"]),
    ("PORTER",         ["porter"]),
    ("BARLEYWINE",     ["barleywine", "barley wine"]),
    ("PILSNER",        ["pilsner", "pilsener", " pils "]),
    ("LAGER",          ["lager", "helles"]),
    ("WEIZEN",         ["weizen", "weisse", "witbier", "hvedeoel"]),
    ("SAISON",         ["saison", "farmhouse"]),
    ("GUEUZE",         ["gueuze", "lambic"]),  # delt ud fra SOUR
    ("SOUR",           ["sour", "gose", "berliner"]),
    ("BOCK",           ["bock"]),
    ("PALE_ALE",       ["pale ale", " apa "]),
    ("BROWN_ALE",      ["brown ale"]),
    ("BLONDE",         ["blonde ale", "blond ale"]),
    ("AMBER",          ["amber"]),
    ("RADLER",         ["radler", "shandy"]),
    ("ALKOHOLFRI",     ["alkoholfri", "alcohol free", "non-alcoholic", "0,0%", "0.0%"]),
]

SYNONYMS = [
    (r"\btrippel\b", "tripel"),
    (r"\btripple\b", "tripel"),
    (r"\bquadruple\b", "quadrupel"),
    (r"\bwest coast ipa\b", "ipa"),
    (r"\bwcipa\b", "ipa"),
    (r"\bnew england ipa\b", "ipa"),
    (r"\bneipa\b", "ipa"),
    (r"\bhazy ipa\b", "ipa"),
    (r"\bsession ipa\b", "ipa"),
    (r"\bdouble ipa\b", "ipa"),
    (r"\bdipa\b", "ipa"),
    (r"\bimperial ipa\b", "ipa"),
    (r"\bblack ipa\b", "ipa"),
    (r"\bindia pale ale\b", "ipa"),
    (r"\btrappist\b", ""),
    (r"\b(belgisk|dansk|tysk|engelsk|hollandsk|belgian|german|dutch|american)\b", ""),
    (r"\b(premium|classic|original|strong|special)\b", ""),
    (r"\b(oekologisk|organic|eco|bio)\b", ""),
]


MATCH_THRESHOLD = 85.0  # hævet fra 82 for at være strengere


def strip_accents(s: str) -> str:
    return (s.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
             .replace("Æ", "ae").replace("Ø", "oe").replace("Å", "aa")
             .replace("é", "e").replace("è", "e").replace("ê", "e")
             .replace("á", "a").replace("à", "a").replace("â", "a")
             .replace("ü", "u").replace("ö", "o").replace("ä", "a"))


def normalize_for_matching(name: str) -> str:
    if not name:
        return ""
    # Decode HTML entities først (fx &#8211; → –)
    name = unescape(name)
    s = strip_accents(name.lower())
    s = re.sub(r"\d+[.,]?\d*\s?(cl|ml|l|liter)\b\.?", " ", s)
    s = re.sub(r"\d+[.,]\d+\s?%", " ", s)
    s = re.sub(r"\d+\s?%", " ", s)
    s = re.sub(r"[-–—_/|*,.()\[\]]", " ", s)

    for pattern, replacement in SYNONYMS:
        s = re.sub(pattern, replacement, s)

    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def style_fingerprint(name: str) -> set:
    name = unescape(name)
    s = " " + strip_accents(name.lower()) + " "
    s = re.sub(r"[-–—_/|*,.()\[\]]", " ", s)
    found = set()
    for style, keywords in EXCLUSIVE_STYLES:
        for kw in keywords:
            if kw in s:
                found.add(style)
                break
    return found


def styles_compatible(fp_a: set, fp_b: set) -> bool:
    if not fp_a or not fp_b:
        return True
    if fp_a == fp_b:
        return True
    if fp_a.issubset(fp_b) or fp_b.issubset(fp_a):
        return True
    return False


def volumes_compatible(v_a, v_b) -> bool:
    if v_a is None or v_b is None:
        return True
    return abs(v_a - v_b) < 0.5


def abv_compatible(a_a, a_b) -> bool:
    if a_a is None or a_b is None:
        return True
    return abs(a_a - a_b) <= 0.4


_BREWERY_PREFIXES = [
    "brouwerij", "brewery", "bryggeri", "bryggeriet", "brauerei",
    "the ", "het ", "brasserie", "brygghus", "bryghus",
]


def _norm_brewery(b):
    """
    Normaliserer et bryggerinavn så fx 'Brouwerij Tilquin' og 'Tilquin' bliver ens.
    """
    if not b:
        return ""
    s = strip_accents(b.lower()).strip()
    # Fjern generiske ord der varierer mellem shops
    for prefix in _BREWERY_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
    # Fjern interpunktuation
    s = re.sub(r"[-–—_/|*,.()\[\]]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def breweries_compatible(brewery_a, brewery_b, name_a=None, name_b=None) -> bool:
    """
    Hård gate: hvis BEGGE har et bryggeri OG de er forskellige → ikke samme øl.
    Hvis mindst én mangler bryggeri, så lader vi andre gates afgøre det.

    Robusthed: scrapers udleder ofte bryggeri forkert (fx ved at splitte på " - ").
    Derfor accepterer vi også et match hvis det ene bryggeri-navn faktisk
    findes som et ord i det andet (eller i øllens navn). Det fanger tilfælde
    som 'Westmalle' vs 'Westmalle Trappist Trippel'.
    """
    bn_a = _norm_brewery(brewery_a)
    bn_b = _norm_brewery(brewery_b)

    if not bn_a or not bn_b:
        return True  # mindst én mangler — fuzzy/style/abv afgør

    # Standard fuzzy match
    score = max(
        fuzz.ratio(bn_a, bn_b),
        fuzz.token_sort_ratio(bn_a, bn_b),
    )
    if score >= 80:
        return True

    # Robusthed mod dårlig brewery-extraction:
    # Hvis bryggeri-navnet på den ene optræder som ord i den andens navn,
    # er det sandsynligvis samme bryggeri
    tokens_a = set(bn_a.split())
    tokens_b = set(bn_b.split())
    # Mindst ét fælles ord der er længere end 3 tegn (undgår "the", "og" osv.)
    common = {t for t in (tokens_a & tokens_b) if len(t) > 3}
    if common:
        return True

    # Sidste check: hvis vi har navnene, så kig om bryggeri-A's hovedord
    # findes i øllens navn-B og omvendt
    if name_a and name_b:
        name_a_lower = strip_accents(name_a.lower())
        name_b_lower = strip_accents(name_b.lower())
        # Tag det første "rigtige" ord fra hvert bryggeri-navn
        for token in bn_a.split():
            if len(token) > 3 and token in name_b_lower:
                return True
        for token in bn_b.split():
            if len(token) > 3 and token in name_a_lower:
                return True

    return False


def _token_count(s: str) -> int:
    return len(s.split()) if s else 0


def similarity_score(name_a, name_b, abv_a, abv_b, brewery_a, brewery_b, fp_a, fp_b):
    """
    Strengere scoring end før.
    - Bruger BÅDE token_sort_ratio (god til ordrækkefølge) OG token_set_ratio
    - Straffer korte navne der har lav reel overlap
    - Bonuses for matchende ABV/bryggeri/stil

    Filosofi: når flere uafhængige hårde signaler matcher præcist
    (samme bryggeri + samme ABV + samme stil + samme volume) er det meget
    usandsynligt at det er to forskellige øl. Derfor giver vi en stor combo-bonus.
    """
    if not name_a or not name_b:
        return 0.0

    # token_set_ratio er meget tilgivende ved længdeforskelle.
    # token_sort_ratio er mere konservativ.
    # Vi bruger gennemsnittet — det balancerer mellem at fange varianter
    # som "tripel tripel westmalle" vs "westmalle tripel" og at undgå
    # falsk match som "gueuze" vs "tilquin gueuze ancienne cuvee arthur".
    ts_set = fuzz.token_set_ratio(name_a, name_b)
    ts_sort = fuzz.token_sort_ratio(name_a, name_b)
    base = (ts_set + ts_sort) / 2

    # Hvis navnene er VÆSENTLIGT forskellige i længde, så bør vi være ekstra strenge.
    # Eksempel: "gueuze" (1 token) vs "tilquin gueuze ancienne cuvee arthur" (5 tokens)
    tc_a = _token_count(name_a)
    tc_b = _token_count(name_b)
    if tc_a > 0 and tc_b > 0:
        ratio = min(tc_a, tc_b) / max(tc_a, tc_b)
        if ratio < 0.5:
            base -= 15
        elif ratio < 0.7:
            base -= 5

    # Tæl hvor mange uafhængige hårde signaler der matcher præcist
    strong_signals = 0

    # Bonuses
    if abv_a is not None and abv_b is not None:
        diff = abs(abv_a - abv_b)
        if diff <= 0.1:
            base += 8
            strong_signals += 1
        elif diff <= 0.3:
            base += 4

    if brewery_a and brewery_b:
        bn_a = _norm_brewery(brewery_a)
        bn_b = _norm_brewery(brewery_b)
        if bn_a and bn_b:
            score = max(fuzz.ratio(bn_a, bn_b), fuzz.token_sort_ratio(bn_a, bn_b))
            if score >= 90:
                base += 8
                strong_signals += 1
            elif score >= 70:
                base += 4

    if fp_a and fp_b and fp_a == fp_b:
        base += 4
        strong_signals += 1

    # Combo-bonus: hvis 3+ uafhængige signaler matcher præcist, er det med
    # meget høj sandsynlighed samme øl
    if strong_signals >= 3:
        base += 6
    elif strong_signals >= 2:
        base += 3

    return base