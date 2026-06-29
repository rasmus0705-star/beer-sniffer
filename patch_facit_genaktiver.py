import shutil, os, sys

# ---------- 1. Flyt overrides.py fra _arkiv tilbage til app/utils ----------
SRC = "_arkiv/overrides.py"
DST = "app/utils/overrides.py"
if not os.path.exists(SRC):
    print(f"FEJL: {SRC} findes ikke. Stopper.")
    sys.exit(1)
if os.path.exists(DST):
    print(f"ADVARSEL: {DST} findes allerede. Stopper (ryd op manuelt).")
    sys.exit(1)
shutil.copy(SRC, DST)
print(f"OK: kopieret {SRC} -> {DST}")

# ---------- 2. Fjern pack-antal-flagning i overrides.py ----------
with open(DST, "r", encoding="utf-8") as f:
    ov = f.read()
pack_block = """    # pak-antal kun hvis navnet ligner et multipak men antal ikke er sat
    if _clean(item.get("pack_count")) is None and looks_like_multipack(item.get("name")):
        miss.append("pak-antal")
"""
if pack_block in ov:
    ov = ov.replace(pack_block, "    # pak-antal flages IKKE laengere (scrapere saetter det ikke - override bevares dog)\n")
    with open(DST, "w", encoding="utf-8") as f:
        f.write(ov)
    print("OK: pack-antal-flagning fjernet (pack_count bevares som override)")
else:
    print("ADVARSEL: pack-antal-blok ikke fundet praecist - tjek manuelt. Fortsaetter.")

# ---------- 3. Patch build_data.py ----------
BD = "build_data.py"
shutil.copy(BD, BD + ".bak")
print(f"OK: backup {BD}.bak")
with open(BD, "r", encoding="utf-8") as f:
    src = f.read()

# 3a. import
imp_anchor = "from app.services.ingest import ingest_batch\n"
imp_new = imp_anchor + "from app.utils.overrides import load_fejlliste, apply_overrides, write_fejlliste\n"
if imp_anchor not in src:
    print("FEJL: import-anker ikke fundet. Stopper - ingen aendringer i build_data.py.")
    sys.exit(1)
src = src.replace(imp_anchor, imp_new, 1)

# 3b. override-loekke FOER ingest
loop_anchor = '''    # 2. Gem i Supabase (bevarer historik)
    print(f"\\n'''
# vi ankrer paa kommentaren + selve gem-printet er ikke noedvendigt; brug en mere unik streng
loop_anchor2 = "    # 2. Gem i Supabase (bevarer historik)\n"
loop_new = '''    # 1b. Facitliste: anvend manuelle overrides FOER matchning (facit vinder)
    print(f"\\n\\U0001F4D8 Anvender facitliste (fejlliste.xlsx)...")
    _facit = load_fejlliste("fejlliste.xlsx")
    for _it in items:
        apply_overrides(_it, _facit)
    print(f"   {len(_facit)} kendte rettelser i facit")

    # 2. Gem i Supabase (bevarer historik)
'''
if loop_anchor2 not in src:
    print("FEJL: ingest-anker ikke fundet. Stopper.")
    sys.exit(1)
src = src.replace(loop_anchor2, loop_new, 1)

# 3c. write_fejlliste EFTER json.dump
dump_anchor = '''    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
'''
dump_new = dump_anchor + '''
    # 7. Opdater facitliste (bevarer dine rettelser, flagger nye huller)
    _stats = write_fejlliste(items, _facit, "fejlliste.xlsx")
    print(f"\\U0001F4DD fejlliste.xlsx opdateret: {_stats['rows']} raekker, {_stats['mangler']} mangler")
'''
if dump_anchor not in src:
    print("FEJL: json.dump-anker ikke fundet. Stopper.")
    sys.exit(1)
src = src.replace(dump_anchor, dump_new, 1)

with open(BD, "w", encoding="utf-8") as f:
    f.write(src)
print("OK: build_data.py patchet (import + override-loekke + write_fejlliste)")
print("Faerdig.")
