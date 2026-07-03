"""
app/utils/description.py — Renser body_html/description-tekst fra scraperne
til brugbare, unikke ølbeskrivelser.

Kasserer teksten HELT hvis den efter rensning er for kort eller tom, i
stedet for at vise et halvfærdigt resultat. Håndterer også Google
Docs-copy/paste-rester (jsaction, jscontroller, data-sfc-* attributter),
som er set i rigtig data fra en af butikkerne.
"""
import re
from html import unescape

MIN_LENGTH = 40       # kortere end dette = ikke værd at vise
MAX_LENGTH = 600       # klip lange beskrivelser af pænt ved sætningsgrænse

# Rene tal/spec-linjer der ikke tilføjer noget ("50 cl. 14,1 %", eller "14,1 %" alene)
_RE_SPEC_ONLY_LINE = re.compile(
    r"^\s*\d+(?:[.,]\d+)?\s*((cl|ml|l)\.?\s*\d*(?:[.,]\d+)?\s*%?|%)\s*$",
    re.IGNORECASE,
)

# Google Docs/Google Sans copy-paste-rester der nogle gange følger med
_RE_GOOGLE_CRUFT_ATTRS = re.compile(
    r'\s*(jsaction|jscontroller|jsuid|data-sfc-[a-z-]+)="[^"]*"', re.IGNORECASE
)

# Label:værdi-par der gentager info allerede vist som separate badges på
# siden (type, ABV, volumen) — fjernes. Hvert mønster er afgrænset til sit
# EGET forventede format, så det ikke ved et uheld æder rigtig prosa, hvis
# der ikke er en ny label at stoppe ved. Andre labels (Country, Untappd
# Ratings, Brewery Notes/humle-info) beholdes, da de er unik værdi.
_RE_REDUNDANT_LABELS = re.compile(
    r"\b(?:Type|Style)\s*:\s*[A-Za-zÀ-ÿ0-9(),/&\- ]{0,60}?"
    r"(?=\s+(?:Alcohol|ABV|Size|Country|Untappd|Brewery)\s*:|\.\s|$)"
    r"|\b(?:Alcohol|ABV)\s*:\s*\d+(?:[.,]\d+)?\s*%"
    r"|\bSize\s*:\s*\d+(?:[.,]\d+)?\s*(?:ml|cl|l)\.?",
    re.IGNORECASE,
)


def _dedupe_sentences(lines):
    """Fjerner gentagne sætninger (samme sætning optræder flere gange i
    samme tekst — set i rigtig data fra Vild med Vin, formentlig en fejl
    i deres eget indholdssystem). Sammenligner uden hensyn til store/små
    bogstaver og tegnsætning, beholder kun første forekomst."""
    seen = set()
    result = []
    for line in lines:
        key = re.sub(r"[^\w\s]", "", line.strip().lower())
        key = re.sub(r"\s+", " ", key)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(line)
    return result


def clean_description(raw_html):
    """Returnerer en ren, brugbar beskrivelse — eller None hvis der ikke
    er noget værd at vise efter rensning."""
    if not raw_html:
        return None

    text = _RE_GOOGLE_CRUFT_ATTRS.sub("", raw_html)
    text = re.sub(r"<a\s[^>]*>.*?</a>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"<[a-zA-Z/][^<]*$", " ", text)  # dangling/unlukket tag i slutningen
    text = unescape(text)
    text = _RE_REDUNDANT_LABELS.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()

    lines = [l.strip() for l in re.split(r"(?<=[.!?])(?=\s|[A-ZÆØÅ])", text) if l.strip()]
    lines = [l for l in lines if not _RE_SPEC_ONLY_LINE.match(l)]
    lines = _dedupe_sentences(lines)
    text = " ".join(lines).strip()

    if len(text) < MIN_LENGTH:
        return None

    if len(text) > MAX_LENGTH:
        cut = text[:MAX_LENGTH]
        last_period = cut.rfind(". ")
        text = cut[:last_period + 1] if last_period > MIN_LENGTH else cut.rstrip() + "…"

    return text


if __name__ == "__main__":
    samples = [
        ("Goose Island Bourbon County (god tekst)", """
        <p><span>(2023) Bourbon County Brand Original Stout</span></p>
        <p>Lagret i gennemsnit 12 måneder på friske bourbonfade fra Buffalo Trace, Heaven Hill, Four Roses og Wild Turkey. </p>
        <p>Denne klassiske imperial stout byder på dybe, komplekse smagsnoter af fudge, vanilje og karamelliseret sukker, pakket ind i en rig og dekadent mundfylde.<br><span></span></p>
        <p><span>50 cl. 14,1 %</span></p>
        <p><a href="https://untappd.com/b/goose-island-beer-co-bourbon-county-brand-stout-2023/5524002" target="_
        """),
        ("Fanø bundle (for kort)", "<p>Black og Red Wedding 2026</p>"),
        ("Google Docs-rod (skal renses)", """
        <p><strong class="Yjhzub" jsaction="" jscontroller="zYmgkd#vvzi1e" data-sfc-root="ep" jsuid="RuXiPb_h" data-sfc-cb="" data-copy-service-computed-style='font-family: "Google Sans"'>MAMA Lemon ØKO</strong><span> (også kendt som </span><strong class="Yjhzub" jsaction="" jscontroller="zYmgkd#vvzi1e" data-sfc-root="ep" jsuid="RuXiPb_i" data-sfc-cb="">en forfriskende økologisk lemonade lavet på modne appelsiner og afrundet med et friskt strejf af citron, med hele 19 procent frugtindhold.</strong></p>
        """),
        ("Kun spec, ingen prosa", "<p>50 cl. 14,1 %</p>"),
        ("Tom", ""),
    ]

    for label, raw in samples:
        result = clean_description(raw)
        print(f"--- {label} ---")
        print(result if result else "(KASSERET — ingen brugbar tekst)")
        print()