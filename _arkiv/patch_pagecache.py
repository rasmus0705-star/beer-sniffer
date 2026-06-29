import shutil, sys

FILES = {
    "app/scrapers/oeltanken.py": {
        "tag": "oeltanken",
        "url_var": "product_url",
        "gate": """            if not is_smagekasse and (volume is None or abv is None):
                p_vol, p_abv = _fetch_from_page(product_url)
                if volume is None and p_vol is not None:
                    volume = p_vol
                if abv is None and p_abv is not None:
                    abv = p_abv
                time.sleep(SIDE_PAUSE)""",
        "indent": "            ",
    },
    "app/scrapers/beerme.py": {
        "tag": "beerme",
        "url_var": "url",
        "gate": """        if not is_smagekasse and not _is_glas(name) and (volume is None or abv is None):
            p_vol, p_abv = _fetch_from_page(url)
            if volume is None and p_vol is not None:
                volume = p_vol
            if abv is None and p_abv is not None:
                abv = p_abv
            time.sleep(SIDE_PAUSE)""",
        "indent": "        ",
    },
}

CACHE_HELPERS = '''
# --- PERF: persistent volumen/ABV-cache (vol/abv aendrer sig aldrig pr. produkt) ---
import json as _json, os as _os
_CACHE_PATH = _os.path.join(_os.path.dirname(__file__), "_pagecache_{tag}.json")
_page_cache = {{}}
_cache_hits = 0
_cache_fetches = 0
try:
    with open(_CACHE_PATH, "r", encoding="utf-8") as _cf:
        _page_cache = _json.load(_cf)
except Exception:
    _page_cache = {{}}

def _cache_save():
    try:
        with open(_CACHE_PATH, "w", encoding="utf-8") as _cf:
            _json.dump(_page_cache, _cf)
    except Exception as _e:
        print(f"  cache-gem fejlede: {{_e}}")
'''

NEW_GATE = '''{indent_strip}# SIDEHENTNING med cache: spring over hvis vi allerede har begge vaerdier
{indent}_key = {url_var}
{indent}_cached = _page_cache.get(_key)
{indent}_need_fetch = (not is_smagekasse{glas_extra}) and (volume is None or abv is None)
{indent}if _need_fetch and _cached:
{indent}    if volume is None and _cached.get("vol") is not None:
{indent}        volume = _cached["vol"]
{indent}    if abv is None and _cached.get("abv") is not None:
{indent}        abv = _cached["abv"]
{indent}    _need_fetch = (volume is None or abv is None)
{indent}if _need_fetch and _cached:
{indent}    global _cache_hits
{indent}    _cache_hits += 1
{indent}if _need_fetch:
{indent}    p_vol, p_abv = _fetch_from_page({url_var})
{indent}    global _cache_fetches
{indent}    _cache_fetches += 1
{indent}    if volume is None and p_vol is not None:
{indent}        volume = p_vol
{indent}    if abv is None and p_abv is not None:
{indent}        abv = p_abv
{indent}    _merged = dict(_cached or {{}})
{indent}    if volume is not None:
{indent}        _merged["vol"] = volume
{indent}    if abv is not None:
{indent}        _merged["abv"] = abv
{indent}    if _merged:
{indent}        _page_cache[_key] = _merged
{indent}    time.sleep(SIDE_PAUSE)
{indent}elif _cached:
{indent}    _cache_hits += 1'''

for path, cfg in FILES.items():
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()

    if "_page_cache" in src:
        print(f"SKIP {path}: ser allerede patchet ud.")
        continue
    if cfg["gate"] not in src:
        print(f"FEJL {path}: fandt ikke gate-blokken praecist. Springer denne fil over.")
        continue

    shutil.copy(path, path + ".bak")

    # 1) saenk pause
    src = src.replace("SIDE_PAUSE = 0.5", "SIDE_PAUSE = 0.2", 1)

    # 2) indsaet cache-helpers efter detect_type-importen
    imp = "from app.utils.detect_type import detect_type\n"
    src = src.replace(imp, imp + CACHE_HELPERS.format(tag=cfg["tag"]), 1)

    # 3) erstat gate
    glas_extra = " and not _is_glas(name)" if cfg["tag"] == "beerme" else ""
    new_gate = NEW_GATE.format(
        indent=cfg["indent"],
        indent_strip=cfg["indent"],
        url_var=cfg["url_var"],
        glas_extra=glas_extra,
    )
    src = src.replace(cfg["gate"], new_gate, 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"OK {path}: pause->0.2, cache indsat, gate erstattet. Backup: {path}.bak")

print("Faerdig. Husk at scraperne nu skal kalde _cache_save() til sidst - tjekkes naeste skridt.")
