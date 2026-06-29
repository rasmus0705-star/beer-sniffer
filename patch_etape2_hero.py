"""
ETAPE 2 — Rent hero med søgefeltet som midtpunkt.

Best practice for søgedrevne sites: ét dominerende handlingselement,
minimal tekst omkring det, ingen dobbelt-budskab.

Ændringer:
  1. Fjern hero-titlen (headeren har allerede brandets løfte — ingen dobbelthed).
  2. Fjern butiksantal fra underteksten; behold antal øl + "opdateret dagligt".
  3. Giv søgefeltet mere vægt (lidt større, tydeligere fokus-glød).
  4. Stram afstandene så søgefeltet kommer højere op.

Kør:  python patch_hero.py
Laver backup index.html.bak2 først.
"""
import io, shutil

FILE = "index.html"
shutil.copy(FILE, FILE + ".bak2")
s = io.open(FILE, encoding="utf-8").read()
ok = True

def patch(old, new, navn):
    global s, ok
    n = s.count(old)
    if n == 0:
        print(f"  [SPRINGER OVER] {navn} — fandt ikke teksten")
        ok = False
    elif n > 1:
        print(f"  [ADVARSEL] {navn} — teksten findes {n} gange (ikke unik)")
        ok = False
    else:
        s = s.replace(old, new)
        print(f"  [OK] {navn}")

# ── 1. CSS: strammere hero + stærkere søgefelt ────────────────────────
gammel_css = """        .hero-search { background: var(--surface); border-bottom: 1px solid var(--border); padding: 1.8rem 2rem 1.2rem; }
        .hero-search-inner { max-width: 900px; margin: 0 auto; text-align: center; }
        .hero-search-title {
            font-family: 'Bebas Neue', sans-serif;
            font-size: 1.8rem;
            color: var(--gold-light);
            letter-spacing: 0.06em;
            margin-bottom: 0.1rem;
        }
        .hero-search-sub { font-size: 0.78rem; color: var(--text-muted); margin-bottom: 1rem; }
        .hero-search-wrap { position: relative; max-width: 560px; margin: 0 auto; }
        .hero-search-wrap svg {
            position: absolute;
            left: 1.2rem;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-muted);
            width: 20px;
            height: 20px;
        }
        .hero-search-input {
            width: 100%;
            background: var(--surface2);
            border: 2px solid var(--border-light);
            border-radius: 14px;
            padding: 1rem 1.2rem 1rem 3.2rem;
            color: var(--text);
            font-family: 'DM Sans', sans-serif;
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        .hero-search-input:focus,
        .hero-search-input:focus-visible { border-color: var(--gold); box-shadow: 0 0 30px rgba(200,146,14,0.15); }
        .hero-search-input::placeholder { color: var(--text-muted); }"""

ny_css = """        /* ── RENT HERO — søgefeltet er midtpunktet ── */
        .hero-search { background: var(--surface); border-bottom: 1px solid var(--border); padding: 1.5rem 2rem 1.3rem; }
        .hero-search-inner { max-width: 900px; margin: 0 auto; text-align: center; }
        .hero-search-sub {
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-bottom: 0.9rem;
            letter-spacing: 0.02em;
        }
        .hero-search-sub strong { color: var(--gold-light); font-weight: 700; }
        .hero-search-wrap { position: relative; max-width: 600px; margin: 0 auto; }
        .hero-search-wrap svg {
            position: absolute;
            left: 1.3rem;
            top: 50%;
            transform: translateY(-50%);
            color: var(--gold-dim);
            width: 22px;
            height: 22px;
            transition: color 0.2s;
        }
        .hero-search-wrap:focus-within svg { color: var(--gold); }
        .hero-search-input {
            width: 100%;
            background: var(--surface2);
            border: 2px solid var(--border-light);
            border-radius: 16px;
            padding: 1.15rem 1.3rem 1.15rem 3.5rem;
            color: var(--text);
            font-family: 'DM Sans', sans-serif;
            font-size: 1.05rem;
            outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        .hero-search-input:focus,
        .hero-search-input:focus-visible {
            border-color: var(--gold);
            box-shadow: 0 0 0 4px rgba(200,146,14,0.12), 0 8px 30px rgba(200,146,14,0.18);
        }
        .hero-search-input::placeholder { color: var(--text-muted); }"""

patch(gammel_css, ny_css, "CSS hero + søgefelt")

# ── 2. HTML: fjern hero-titel + butiksantal ───────────────────────────
gammel_html = """    <div class="hero-search-inner">
        <h2 class="hero-search-title">Find den billigste øl — på få sekunder</h2>
        <p class="hero-search-sub">Søg blandt <strong id="hero-beer-count">2.300+</strong> øl fra <strong>7 butikker</strong> — opdateret dagligt</p>
        <div class="hero-search-wrap">"""

ny_html = """    <div class="hero-search-inner">
        <p class="hero-search-sub">Søg blandt <strong id="hero-beer-count">2.300+</strong> øl — opdateret dagligt</p>
        <div class="hero-search-wrap">"""

patch(gammel_html, ny_html, "HTML hero-titel + butiksantal fjernet")

# ── 3. Mobil-CSS: ryd op efter fjernet titel ──────────────────────────
gammel_mobil = """            .hero-search { padding: 1.2rem 1rem 0.8rem; }
            .hero-search-title { font-size: 1.4rem; }
            .cat-btn { font-size: 0.76rem; padding: 0.45rem 0.8rem; }"""

ny_mobil = """            .hero-search { padding: 1.1rem 1rem 0.9rem; }
            .hero-search-input { font-size: 1rem; padding: 1rem 1.1rem 1rem 3.2rem; }
            .cat-btn { font-size: 0.76rem; padding: 0.45rem 0.8rem; }"""

patch(gammel_mobil, ny_mobil, "Mobil-CSS hero")

# ── Gem ───────────────────────────────────────────────────────────────
if ok:
    io.open(FILE, "w", encoding="utf-8").write(s)
    print("\n✅ Etape 2 færdig — rent hero. Backup: index.html.bak2")
    print("   Åbn index.html og se resultatet.")
else:
    print("\n⚠️  En eller flere patches sprunget over — INTET gemt. Filen er urørt.")