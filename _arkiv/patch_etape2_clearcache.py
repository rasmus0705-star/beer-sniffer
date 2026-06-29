import shutil, sys

PATH = "app/services/ingest.py"
BACKUP = PATH + ".bak"

with open(PATH, "r", encoding="utf-8") as f:
    lines = f.readlines()

hits = [i for i, l in enumerate(lines) if "from app.routers.beers import clear_cache" in l]

if len(hits) == 0:
    print("❌ Fandt IKKE import-linjen. Ingen ændringer foretaget.")
    sys.exit(1)
if len(hits) > 1:
    print(f"⚠️  Fandt {len(hits)} forekomster — forventede 1. Stopper for en sikkerheds skyld.")
    for i in hits:
        print(f"   linje {i+1}: {lines[i].rstrip()}")
    sys.exit(1)

shutil.copy(PATH, BACKUP)
print(f"💾 Backup gemt: {BACKUP}")

i = hits[0]
old = lines[i]
indent = old[:len(old) - len(old.lstrip())]
new = f"{indent}clear_cache = lambda: None  # statisk pipeline - ingen server-cache at rydde (FastAPI-routers fjernet)\n"
lines[i] = new

print("\n🔧 Ændring (linje {}):".format(i + 1))
print(f"   FOER:  {old.rstrip()}")
print(f"   EFTER: {new.rstrip()}")

with open(PATH, "w", encoding="utf-8") as f:
    f.writelines(lines)

print("\n✅ Patch anvendt. routers-afhaengigheden er klippet.")