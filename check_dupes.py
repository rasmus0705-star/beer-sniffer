import json

with open('data.json', encoding='utf-8') as f:
    data = json.load(f)

multi = [b for b in data['beers'] if b.get('shop_count', 1) > 1]
print(f'Øl med flere butikker: {len(multi)}')

for b in multi:
    shops = [p['shop_name'] for p in b['prices']]
    if len(set(shops)) > 1:  # kun hvis det er FORSKELLIGE butikker
        print(f"\n✅ {b['name']}")
        for p in b['prices']:
            print(f"   {p['shop_name']}: {p['price']} kr")
    else:
        print(f"\n⚠️  DUBLET fra samme butik: {b['name']} ({shops[0]})")