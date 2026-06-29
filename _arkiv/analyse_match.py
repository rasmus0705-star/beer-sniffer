import json, re
from collections import defaultdict

data = json.load(open('data.json', encoding='utf-8'))
beers = data['beers']

def norm(s):
    s = (s or '').lower()
    s = re.sub(r'\d+(?:[.,]\d+)?\s*(cl|ml|l|%)', ' ', s)
    s = re.sub(r'[^a-zæøå0-9 ]', ' ', s)
    # fjern almindelige fyldord
    for w in ['trappist','brouwerij','der','van','co','brewing','brewery','the']:
        s = re.sub(rf'\b{w}\b', ' ', s)
    return ' '.join(s.split())

# Grupper potentielt-samme øl: nøgle = (sorterede kerneord i navn, volumen, afrundet abv)
buckets = defaultdict(list)
for b in beers:
    name_words = tuple(sorted(set(norm(b.get('name','')).split())))
    if not name_words:
        continue
    vol = b.get('volume_cl')
    abv = round(b.get('abv') or 0)
    # brug kun de 4 mest "betydende" ord for at fange varianter
    key = (name_words, vol, abv)
    buckets[key].append(b)

# Find buckets med flere SEPARATE grupper (= burde måske være slået sammen)
split_grupper = []
for key, gruppe in buckets.items():
    if len(gruppe) > 1:
        # er de fra forskellige butikker?
        alle_butikker = set()
        for g in gruppe:
            for p in g.get('prices', []):
                alle_butikker.add(p['shop_name'])
        if len(alle_butikker) > 1:
            split_grupper.append((key, gruppe))

print(f"Total grupper i data.json: {len(beers)}")
print(f"Potentielt opsplittede (samme navn+vol+abv, flere grupper, flere butikker): {len(split_grupper)}")
print()
print("=== TOP 15 EKSEMPLER ===\n")
for key, gruppe in sorted(split_grupper, key=lambda x: -len(x[1]))[:15]:
    name_words, vol, abv = key
    print(f"● {' '.join(name_words)[:50]} | {vol}cl | ~{abv}%  ({len(gruppe)} grupper)")
    for g in gruppe:
        bryg = g.get('brewery','?')
        shops = ', '.join(p['shop_name'] for p in g.get('prices',[]))
        print(f"    [{bryg[:30]}] {g['name'][:45]} — {shops}")
    print()