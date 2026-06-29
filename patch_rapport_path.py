import shutil, re
P = "match_rapport.py"
with open(P, encoding="utf-8") as f:
    src = f.read()
old = 'DATA = "data.json"'
new = ('import os as _os\n'
       'DATA = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data.json")')
if old not in src:
    print("FEJL: fandt ikke 'DATA = \"data.json\"'. Stopper.")
elif src.count(old) != 1:
    print(f"ADVARSEL: fandt {src.count(old)} forekomster. Stopper.")
else:
    shutil.copy(P, P + ".bak")
    src = src.replace(old, new, 1)
    with open(P, "w", encoding="utf-8") as f:
        f.write(src)
    print("OK: DATA peger nu paa repo-roden uanset placering. Backup: match_rapport.py.bak")
