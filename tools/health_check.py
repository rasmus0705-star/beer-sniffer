"""Datakvalitets-helbredstjek for alle scrapere.
Read-only: henter feeds og taeller daekningsgrad pr. felt. Skriver INTET til Supabase/data.json.
Koeres fra repo-roden: python tools\health_check.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.scrapers.brygshoppen import scrape_brygshoppen
from app.scrapers.agoodcase import scrape_agoodcase
from app.scrapers.beershoppen import scrape_beershoppen
from app.scrapers.bestofbeers import scrape_bestofbeers
from app.scrapers.oeltanken import scrape_oeltanken
from app.scrapers.beerme import scrape_beerme
from app.scrapers.vildmedvin import scrape_vildmedvin

SCRAPERS = [
    ("Brygshoppen", scrape_brygshoppen),
    ("A Good Case", scrape_agoodcase),
    ("Beershoppen", scrape_beershoppen),
    ("Best of Beers", scrape_bestofbeers),
    ("Oeltanken", scrape_oeltanken),
    ("Beer Me", scrape_beerme),
    ("Vild med Vin", scrape_vildmedvin),
]

CRITICAL = ["name", "price"]          # skal vaere ~100%
IMPORTANT = ["volume_cl", "abv", "brewery"]  # gul under 70%
INFO = ["type", "image", "url"]       # nice-to-have
THRESHOLD = 70

GREEN, YELLOW, RED, GRAY, RESET = "\033[92m", "\033[93m", "\033[91m", "\033[90m", "\033[0m"

def has_value(v):
    if v is None: return False
    if isinstance(v, str) and v.strip() == "": return False
    return True

def pct(items, field):
    if not items: return 0.0
    return 100.0 * sum(1 for it in items if has_value(it.get(field))) / len(items)

def color_for(field, p):
    if field in CRITICAL:
        return GREEN if p >= 99 else RED
    if field in IMPORTANT:
        return GREEN if p >= 90 else (YELLOW if p >= THRESHOLD else RED)
    return GRAY

ALL_FIELDS = CRITICAL + IMPORTANT + INFO
lines_out = []
def emit(s_plain, s_color=None):
    print(s_color if s_color is not None else s_plain)
    lines_out.append(s_plain)

emit("=" * 78)
emit("DATAKVALITETS-HELBREDSTJEK — alle 7 scrapere (fuld koersel)")
emit("=" * 78)

header = f"{'BUTIK':<15}{'n':>5}  " + "  ".join(f"{f[:6]:>6}" for f in ALL_FIELDS)
emit(header)
emit("-" * 78)

problems = {}
for name, fn in SCRAPERS:
    try:
        items = fn()
    except Exception as e:
        emit(f"{name:<15}  FEJL: {e}")
        continue
    row_plain = f"{name:<15}{len(items):>5}  "
    row_color = f"{name:<15}{len(items):>5}  "
    for f in ALL_FIELDS:
        p = pct(items, f)
        cell = f"{p:5.0f}%"
        row_plain += f"{cell:>6}  "
        c = color_for(f, p)
        row_color += f"{c}{cell:>6}{RESET}  "
    print(row_color)
    lines_out.append(row_plain)

    # saml eksempler paa oel der mangler et VIGTIGT felt (ikke smagekasser)
    for f in IMPORTANT:
        missing = [it for it in items
                   if not has_value(it.get(f))
                   and it.get("category") != "smagekasse"]
        if missing and pct(items, f) < 90:
            problems.setdefault(name, []).append((f, missing[:3], len(missing)))

emit("-" * 78)
emit(f"Foklaring: {GREEN}groen=ok{RESET}  {YELLOW}gul=under 90%{RESET}  {RED}roed=under {THRESHOLD}% (vigtig) / kritisk{RESET}  {GRAY}graa=info{RESET}".replace(GREEN,"").replace(YELLOW,"").replace(RED,"").replace(GRAY,"").replace(RESET,""))
emit("")

if problems:
    emit("KONKRETE HULLER (enkeltoel, ikke smagekasser) — kig om det er aegte fejl:")
    emit("")
    for shop, issues in problems.items():
        emit(f"  {shop}:")
        for field, examples, total in issues:
            emit(f"    mangler '{field}' ({total} stk), fx:")
            for ex in examples:
                emit(f"       - {ex.get('name','?')[:60]}")
        emit("")
else:
    emit("Ingen vigtige felter under taersklen paa enkeltoel. Alt ser sundt ud.")

report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "health_report.txt")
with open(report_path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines_out))
emit("")
emit(f"Rapport gemt: {report_path}")
