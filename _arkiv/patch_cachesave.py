import shutil, sys

TARGETS = {
    "app/scrapers/oeltanken.py": "oeltanken",
    "app/scrapers/beerme.py": "beerme",
}

ANCHOR = '    return items\nif __name__ == "__main__":'

NEW = '''    _cache_save()
    print(f"  [{tag}] sidehentning: {{_cache_fetches}} hentet, {{_cache_hits}} fra cache")
    return items
if __name__ == "__main__":'''

for path, tag in TARGETS.items():
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    if "_cache_save()" in src and "sidehentning:" in src:
        print(f"SKIP {path}: ser allerede ud til at gemme cachen.")
        continue
    if ANCHOR not in src:
        print(f"FEJL {path}: fandt ikke 'return items' + __main__ anker. Springer over.")
        continue
    if src.count(ANCHOR) != 1:
        print(f"ADVARSEL {path}: anker findes {src.count(ANCHOR)} gange - forventede 1. Springer over.")
        continue

    shutil.copy(path, path + ".bak2")
    src = src.replace(ANCHOR, NEW.format(tag=tag), 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"OK {path}: _cache_save() + tael-print indsat. Backup: {path}.bak2")

print("Faerdig.")
