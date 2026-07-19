"""
Fælles matching-logik for ølprodukter.
Bruges af både ingest.py (når øl gemmes) og beers.py (når øl grupperes).

VIGTIGT: ændringer her påvirker BÅDE hvordan øl gemmes OG hvordan de grupperes.

FILOSOFI om manglende data:
Tidligere lod vi None-værdier "slippe gennem" gates (volume/ABV/brewery).
Det førte til falske matches når scrapers ikke kunne udlede data fra navnet.
Nu kræver vi DET MODSATTE: jo mere data der mangler, jo HØJERE fuzzy-score
skal navnet have for at blive matched.
"""
import re
from rapidfuzz import fuzz
from html import unescape


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
    ("GUEUZE",         ["gueuze", "lambic"]),
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


MATCH_THRESHOLD = 85.0  # base threshold når alle data er kendt


# Ord der ikke tæller som "meningsfuldt overlap" — generiske ølord
_STOP_WORDS = {
    "beer", "ale", "lager", "pils", "pilsner", "stout", "porter",
    "tripel", "trippel", "tripple", "dubbel", "ipa", "apa",
    "blond", "blonde", "amber", "barrel", "aged", "imperial",
    "session", "double", "single", "extra", "strong", "old",
    "new", "white", "black", "red", "brown", "gold", "golden",
    "dark", "light", "barley", "wine", "sour", "gose", "saison",
    "weizen", "weisse", "witbier", "lambic", "gueuze", "bock",
    "trappist", "abbey", "premium", "classic", "original",
    "draft", "draught", "fresh", "smooth", "hoppy", "malt", "malty",
    "the", "with", "and", "from", "for",
}


_VARIANT_WORDS = {
    "barrel", "ba", "bourbon", "whisky", "whiskey", "cognac", "rum",
    "wine", "reserva", "reserve", "vintage", "anniversary", "jubilaeum",
    "jubilæum", "calvados", "tequila", "armagnac", "sherry", "port",
}


def strip_accents(s: str) -> str:
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


def normalize_for_matching(name: str) -> str:
    if not name:
        return ""
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
    """Hård gate når begge kendt. None accepteres for nu — håndteres i score."""
    if v_a is None or v_b is None:
        return True
    return abs(v_a - v_b) < 0.5


def abv_compatible(a_a, a_b) -> bool:
    """Hård gate når begge kendt. None accepteres for nu — håndteres i score."""
    if a_a is None or a_b is None:
        return True
    return abs(a_a - a_b) <= 0.4


_BREWERY_PREFIXES = [
    "brouwerij", "brewery", "bryggeri", "bryggeriet", "brauerei",
    "the ", "het ", "brasserie", "brygghus", "bryghus",
]


def _variant_markers(name):
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


# Bryggeri-aliaser: {normaliseret_fra: normaliseret_til}. Tom indtil build_data/
# generatoren injicerer via set_brewery_aliases(). Undgaar cirkulaer import.
_BREWERY_ALIASES = {}

def set_brewery_aliases(mapping):
    """Injicer alias-map (allerede normaliserede noegler). Kaldes ved opstart."""
    global _BREWERY_ALIASES
    _BREWERY_ALIASES = dict(mapping or {})


_BREWERY_SUFFIXES = {
    "brewing", "brewery", "brewers", "brew",
    "co", "company", "craft",
}


def _norm_brewery(b):
    if not b:
        return ""
    s = strip_accents(b.lower()).strip()
    for prefix in _BREWERY_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix):].strip()
    s = s.replace("\u2019", "'").replace("\u02bc", "'")  # kroellet apostrof -> lige
    s = s.replace("'", "")                                 # fjern apostrof helt
    s = re.sub(r"[-–—_/|*,.()\[\]]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    toks = s.split()
    while len(toks) > 1 and toks[-1] in _BREWERY_SUFFIXES:
        toks.pop()
    s = " ".join(toks)
    s = _BREWERY_ALIASES.get(s, s)   # manuel alias vinder til sidst
    return s


def breweries_compatible(brewery_a, brewery_b, name_a=None, name_b=None) -> bool:
    """
    Hård gate når begge har bryggeri.
    Hvis én mangler bryggeri → tjek om bryggeri-navnet findes i begge øl-navne.
    Hvis ingen kan bekræftes → lad score afgøre (strengere threshold).
    """
    bn_a = _norm_brewery(brewery_a)
    bn_b = _norm_brewery(brewery_b)

    # Hvis begge kendt: standard fuzzy match
    if bn_a and bn_b:
        score = max(
            fuzz.ratio(bn_a, bn_b),
            fuzz.token_sort_ratio(bn_a, bn_b),
        )
        if score >= 80:
            return True
        # Eller fælles meningsfulde ord
        tokens_a = set(bn_a.split())
        tokens_b = set(bn_b.split())
        common = {t for t in (tokens_a & tokens_b) if len(t) > 3 and t not in _STOP_WORDS}
        if common:
            return True
        # Eller bryggeri-A optræder i øl-B's navn
        if name_a and name_b:
            name_a_lower = strip_accents(name_a.lower())
            name_b_lower = strip_accents(name_b.lower())
            for token in bn_a.split():
                if len(token) > 3 and token not in _STOP_WORDS and token in name_b_lower:
                    return True
            for token in bn_b.split():
                if len(token) > 3 and token not in _STOP_WORDS and token in name_a_lower:
                    return True
        return False

    # Hvis én mangler bryggeri: KRÆV at det kendte bryggeri findes i begge navne
    known_brewery = bn_a or bn_b
    if known_brewery and name_a and name_b:
        name_a_lower = strip_accents(name_a.lower())
        name_b_lower = strip_accents(name_b.lower())
        for token in known_brewery.split():
            if len(token) > 3 and token not in _STOP_WORDS:
                # Bryggeri-token skal findes i BEGGE øl-navne
                if token in name_a_lower and token in name_b_lower:
                    return True
        return False

    # Hvis ingen bryggeri-info overhovedet — lad score afgøre
    return True


def _meaningful_tokens(name: str) -> set:
    """Returnerer tokens fra navnet der ikke er generiske ølord eller for korte."""
    if not name:
        return set()
    norm = normalize_for_matching(name)
    return {t for t in norm.split() if len(t) > 3 and t not in _STOP_WORDS}


def has_meaningful_overlap(name_a: str, name_b: str) -> bool:
    """
    Mandatory check: navnene skal dele mindst ét meningsfuldt ord.
    Forhindrer at to helt forskellige øl matches blot fordi de begge er fx "Imperial Stout".
    """
    tokens_a = _meaningful_tokens(name_a)
    tokens_b = _meaningful_tokens(name_b)
    return bool(tokens_a & tokens_b)


def _token_count(s: str) -> int:
    return len(s.split()) if s else 0


def similarity_score(name_a, name_b, abv_a, abv_b, brewery_a, brewery_b, fp_a, fp_b):
    """
    Standard score 0-100+ baseret på navne med bonuses.
    """
    if not name_a or not name_b:
        return 0.0

    ts_set = fuzz.token_set_ratio(name_a, name_b)
    ts_sort = fuzz.token_sort_ratio(name_a, name_b)
    base = (ts_set + ts_sort) / 2

    # Fjern bryggeri-tokens fra navnene FOER laengde-strafen. Nogle kilder
    # (fx Vild med Vin) skriver bryggeriet ind i selve navnet, saa navnet
    # bliver kunstigt laengere og udloeser en falsk laengde-straf — selv om
    # det ekstra netop er bryggeriet, der allerede matcher.
    _brew_tokens = set()
    for _bw in (brewery_a, brewery_b):
        if _bw:
            _brew_tokens |= set(normalize_for_matching(_bw).split())
    tc_a = len([t for t in name_a.split() if t not in _brew_tokens])
    tc_b = len([t for t in name_b.split() if t not in _brew_tokens])
    if tc_a > 0 and tc_b > 0:
        ratio = min(tc_a, tc_b) / max(tc_a, tc_b)
        if ratio < 0.5:
            base -= 15
        elif ratio < 0.7:
            base -= 5

    strong_signals = 0

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

    if strong_signals >= 3:
        base += 6
    elif strong_signals >= 2:
        base += 3

    return base


def required_threshold(abv_a, abv_b, vol_a, vol_b, brewery_a, brewery_b):
    """
    Beregner hvor højt fuzzy-scoren skal være for at en match accepteres.
    Jo mere data der mangler, jo strengere bliver kravet.

    - Alle data kendt: 85 (base)
    - 1 data mangler: 90
    - 2 data mangler: 95
    - 3 data mangler: 98 (næsten kun ved identiske navne)
    """
    missing = 0
    if abv_a is None or abv_b is None:
        missing += 1
    if vol_a is None or vol_b is None:
        missing += 1
    if not _norm_brewery(brewery_a) or not _norm_brewery(brewery_b):
        missing += 1

    if missing == 0:
        return 85.0
    elif missing == 1:
        return 90.0
    elif missing == 2:
        return 95.0
    else:
        return 98.0