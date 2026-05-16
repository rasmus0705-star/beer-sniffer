"""
Fælles matching-logik for ølprodukter.
Bruges af både ingest.py (når øl gemmes) og beers.py (når øl grupperes).

Det er KRITISK at begge filer bruger samme logik — ellers kan to øl
matches forskelligt ved ingest og display.
"""
import re
from rapidfuzz import fuzz


# Eksklusive stilarter — to forskellige af disse må ALDRIG merges
# Rækkefølgen betyder noget for entydig fingerprinting
EXCLUSIVE_STYLES = [
    # Belgiske — kritisk at Dubbel/Tripel/Quad ikke forveksles
    ("QUADRUPEL",      ["quadrupel", "quadruple", " quad "]),
    ("TRIPEL",         ["tripel", "trippel", "tripple"]),
    ("DUBBEL",         ["dubbel"]),
    # IPA — alle varianter samles under én paraply
    ("IPA",            ["ipa", "india pale ale"]),
    # Mørke stilarter
    ("IMPERIAL_STOUT", ["imperial stout", "russian imperial"]),
    ("STOUT",          ["stout"]),
    ("PORTER",         ["porter"]),
    ("BARLEYWINE",     ["barleywine", "barley wine"]),
    # Lyse stilarter
    ("PILSNER",        ["pilsner", "pilsener", " pils "]),
    ("LAGER",          ["lager", "helles"]),
    ("WEIZEN",         ["weizen", "weisse", "witbier", "hvedeoel"]),
    ("SAISON",         ["saison", "farmhouse"]),
    ("SOUR",           ["sour", "gose", "lambic", "gueuze", "berliner"]),
    ("BOCK",           ["bock"]),
    ("PALE_ALE",       ["pale ale", " apa "]),
    ("BROWN_ALE",      ["brown ale"]),
    ("BLONDE",         ["blonde ale", "blond ale"]),
    ("AMBER",          ["amber"]),
    ("RADLER",         ["radler", "shandy"]),
    ("ALKOHOLFRI",     ["alkoholfri", "alcohol free", "non-alcoholic", "0,0%", "0.0%"]),
]

# Synonymer der konverteres FØR fuzzy matching
SYNONYMS = [
    # Stavevarianter
    (r"\btrippel\b", "tripel"),
    (r"\btripple\b", "tripel"),
    (r"\bquadruple\b", "quadrupel"),
    # IPA-varianter — alle reduceres til "ipa"
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
    # "trappist" er beskrivelse, ikke ID
    (r"\btrappist\b", ""),
    # Nationaliteter
    (r"\b(belgisk|dansk|tysk|engelsk|hollandsk|belgian|german|dutch|american)\b", ""),
    # Generiske ord
    (r"\b(premium|classic|original|strong|special)\b", ""),
    (r"\b(oekologisk|organic|eco|bio)\b", ""),
]


MATCH_THRESHOLD = 82.0


def strip_accents(s: str) -> str:
    """Konverterer danske/europæiske tegn til ASCII."""
    return (s.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
             .replace("Æ", "ae").replace("Ø", "oe").replace("Å", "aa")
             .replace("é", "e").replace("è", "e").replace("ê", "e")
             .replace("á", "a").replace("à", "a").replace("â", "a")
             .replace("ü", "u").replace("ö", "o").replace("ä", "a"))


def normalize_for_matching(name: str) -> str:
    """
    Aggressiv normalisering — fjerner ALT der ikke er identifikator-info.
    Returnerer den streng der bruges til fuzzy sammenligning.
    """
    if not name:
        return ""

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
    """
    Returnerer sæt af eksklusive stilarter fundet i navnet.
    Hård gate: to øl med konflikterende stilarter må aldrig merges.
    """
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
    """To øl er stil-kompatible hvis ingen konflikt eller delmængde."""
    if not fp_a or not fp_b:
        return True
    if fp_a == fp_b:
        return True
    if fp_a.issubset(fp_b) or fp_b.issubset(fp_a):
        return True
    return False


def volumes_compatible(v_a, v_b) -> bool:
    """Volume er hård gate (None accepteres)."""
    if v_a is None or v_b is None:
        return True
    return abs(v_a - v_b) < 0.5


def abv_compatible(a_a, a_b) -> bool:
    """ABV er hård gate — max 0.4 procentpoint forskel."""
    if a_a is None or a_b is None:
        return True
    return abs(a_a - a_b) <= 0.4


def similarity_score(name_a, name_b, abv_a, abv_b, brewery_a, brewery_b, fp_a, fp_b):
    """Samlet match-score 0-100+ med bonuses for ABV/bryggeri/stil."""
    if not name_a or not name_b:
        return 0.0

    base = fuzz.token_set_ratio(name_a, name_b)

    if abv_a is not None and abv_b is not None:
        diff = abs(abv_a - abv_b)
        if diff <= 0.1:
            base += 8
        elif diff <= 0.3:
            base += 4

    if brewery_a and brewery_b:
        bn_a = strip_accents(brewery_a.lower()).strip()
        bn_b = strip_accents(brewery_b.lower()).strip()
        if bn_a == bn_b and bn_a:
            base += 6

    if fp_a and fp_b and fp_a == fp_b:
        base += 4

    return base