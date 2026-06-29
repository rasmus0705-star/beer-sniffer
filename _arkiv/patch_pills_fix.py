"""
RETTELSE til etape 3b — pills må ikke gemme indhold på desktop.

Problem: vandret-scroll virker med finger på mobil, men IKKE med mus på
desktop (musehjul scroller lodret). Så pills til højre blev utilgængelige.

Løsning: på desktop bryder pills pænt til (højst) to linjer. På touch-mobil
beholder vi den ene scrollbare linje med fade, hvor swipe faktisk virker.

Kør:  python patch_pills_fix.py
Backup: index.html.bakpf
"""
import io, shutil

FILE = "index.html"
shutil.copy(FILE, FILE + ".bakpf")
s = io.open(FILE, encoding="utf-8").read()
ok = True

def patch(old, new, navn):
    global s, ok
    n = s.count(old)
    if n == 0:
        print(f"  [SPRINGER OVER] {navn} — fandt ikke teksten")
        ok = False
    elif n > 1:
        print(f"  [ADVARSEL] {navn} — findes {n} gange (ikke unik)")
        ok = False
    else:
        s = s.replace(old, new)
        print(f"  [OK] {navn}")

# Erstat hele den nuværende category-bar CSS (fra etape 3b) med en
# version der wrapper på desktop og kun scroller på touch.
gammel = """        .category-bar {
            display: flex;
            gap: 0.5rem;
            justify-content: flex-start;
            flex-wrap: nowrap;
            margin-top: 1rem;
            padding-bottom: 0.5rem;
            overflow-x: auto;
            scrollbar-width: none;
            -webkit-overflow-scrolling: touch;
            scroll-snap-type: x proximity;
            -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 24px, #000 calc(100% - 24px), transparent 100%);
            mask-image: linear-gradient(90deg, transparent 0, #000 24px, #000 calc(100% - 24px), transparent 100%);
        }
        .category-bar::-webkit-scrollbar { display: none; }
        .cat-btn { scroll-snap-align: start; }
        /* Centrér pills når der ER plads (få nok til at passe på linjen) */
        @media (min-width: 1101px) {
            .category-bar { justify-content: center; }
        }"""

ny = """        /* DESKTOP (standard): pills wrapper pænt, intet gemmes — mus kan
           ikke scrolle en vandret liste, så alt skal være synligt. */
        .category-bar {
            display: flex;
            gap: 0.5rem;
            justify-content: center;
            flex-wrap: wrap;
            margin-top: 1rem;
            padding-bottom: 0.4rem;
        }
        .category-bar::-webkit-scrollbar { display: none; }

        /* TOUCH-MOBIL: her VIRKER swipe, så vi bruger én ren scrollbar
           linje med fade i kanterne. Kun på pegeskærme. */
        @media (hover: none) and (pointer: coarse) {
            .category-bar {
                flex-wrap: nowrap;
                justify-content: flex-start;
                overflow-x: auto;
                scrollbar-width: none;
                -webkit-overflow-scrolling: touch;
                scroll-snap-type: x proximity;
                -webkit-mask-image: linear-gradient(90deg, transparent 0, #000 24px, #000 calc(100% - 24px), transparent 100%);
                mask-image: linear-gradient(90deg, transparent 0, #000 24px, #000 calc(100% - 24px), transparent 100%);
            }
            .cat-btn { scroll-snap-align: start; }
        }"""

patch(gammel, ny, "Pills: wrap på desktop, scroll på touch")

if ok:
    io.open(FILE, "w", encoding="utf-8").write(s)
    print("\n✅ Rettelse færdig. Backup: index.html.bakpf")
    print("   Test på desktop: gør vinduet smalt — pills skal nu bryde til")
    print("   to linjer (intet gemt til højre), ikke scrolle væk.")
else:
    print("\n⚠️  Patch sprunget over — INTET gemt. Filen er urørt.")