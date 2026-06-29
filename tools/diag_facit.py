import sys, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.utils.overrides import load_fejlliste

facit = load_fejlliste(os.path.join(ROOT, "fejlliste.xlsx"))
print(f"Total rettelser i arket: {len(facit)}\n")

bad_pattern = re.compile(r'best\s*before|holdbar|\d{2}[/-]\d{2}[/-]\d{2,4}|udl[oø]ber', re.I)

with_brewery = 0
bad_brewery = 0
good_brewery_examples = []
bad_brewery_examples = []

for key, rec in facit.items():
    b = rec.get("brewery")
    if b is None:
        continue
    with_brewery += 1
    if bad_pattern.search(str(b)):
        bad_brewery += 1
        if len(bad_brewery_examples) < 5:
            bad_brewery_examples.append((rec.get("name","?"), b))
    else:
        if len(good_brewery_examples) < 5:
            good_brewery_examples.append((rec.get("name","?"), b))

print(f"Raekker med brewery udfyldt: {with_brewery}")
print(f"  - ser FORKERTE ud (dato/best before): {bad_brewery}")
print(f"  - ser korrekte ud:                    {with_brewery - bad_brewery}\n")

print("FORKERTE eksempler:")
for n, b in bad_brewery_examples:
    print(f"   [{b}]  <- {n[:50]}")
print("\nKORREKTE eksempler:")
for n, b in good_brewery_examples:
    print(f"   [{b}]  <- {n[:50]}")
