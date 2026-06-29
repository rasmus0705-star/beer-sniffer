import shutil, re

TARGETS = {
    "app/scrapers/oeltanken.py": "oeltanken",
    "app/scrapers/beerme.py": "beerme",
}

ANCHOR = '\nif __name__ == "__main__":'

for path, tag in TARGETS.items():
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    if "_cache_save()" in src and "sidehentning:" in src:
        print(f"SKIP {path}: allerede patchet.")
        continue
    if src.count(ANCHOR) != 1:
        print(f"FEJL {path}: __main__ anker findes {src.count(ANCHOR)} gange. Springer over.")
        continue

    # find sidste 'return items' FOER __main__
    main_pos = src.index(ANCHOR)
    head = src[:main_pos]
    m = list(re.finditer(r'\n([ \t]*)return items[ \t]*\n', head))
    if not m:
        print(f"FEJL {path}: ingen 'return items' fundet foer __main__. Springer over.")
        continue
    last = m[-1]
    indent = last.group(1)
    inject = f"\n{indent}_cache_save()\n{indent}print(f\"  [{tag}] sidehentning: {{_cache_fetches}} hentet, {{_cache_hits}} fra cache\")\n{indent}return items\n"
    new_src = src[:last.start()] + inject + src[last.end():]

    shutil.copy(path, path + ".bak2")
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_src)
    print(f"OK {path}: cache-save indsat foer afsluttende return (indent={len(indent)} tegn). Backup: .bak2")

print("Faerdig.")
