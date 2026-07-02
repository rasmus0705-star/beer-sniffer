# -*- coding: utf-8 -*-
"""
stamp_data_version.py

Opdaterer DATA_VERSION-konstanten i index.html med et nyt tidsstempel.
Skal køres EFTER hvert build (efter build_data.py har skrevet ny
data.json), så browsere og Cloudflare henter den friske data.json —
og cacher den indtil næste build.

Scriptet er idempotent og sikkert:
  - Finder linjen via regex uanset hvilken version der står der nu
  - Ændrer intet andet i filen
  - Fejler højlydt (exit-kode 1) hvis mønsteret ikke findes, så en
    fejl i pipelinen ikke passerer ubemærket

Kør fra roden af projektet:
    python stamp_data_version.py

Integration (vælg én):
  A) Tilføj i opdater.bat lige efter 'python build_data.py':
         python stamp_data_version.py
     og sørg for at index.html er med i git add-linjen.

  B) Eller tilføj nederst i build_data.py's main-flow:
         import subprocess, sys as _sys
         subprocess.run([_sys.executable, "stamp_data_version.py"], check=True)
"""

import re
import sys
from datetime import datetime

FILE_PATH = "index.html"

PATTERN = re.compile(r"const DATA_VERSION = '[^']*';")


def main():
    try:
        with open(FILE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ stamp_data_version: kunne ikke finde {FILE_PATH}")
        sys.exit(1)

    matches = PATTERN.findall(content)
    if len(matches) != 1:
        print(f"❌ stamp_data_version: fandt {len(matches)} DATA_VERSION-linjer i {FILE_PATH} (kræver 1).")
        print("   Er patch_cache_version.py kørt?")
        sys.exit(1)

    new_version = datetime.now().strftime("%Y%m%d-%H%M")
    new_line = f"const DATA_VERSION = '{new_version}';"

    if matches[0] == new_line:
        print(f"ℹ️  DATA_VERSION er allerede '{new_version}' — ingen ændring.")
        return

    content = PATTERN.sub(new_line, content)
    with open(FILE_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"🏷️  DATA_VERSION stemplet: {new_version}")


if __name__ == "__main__":
    main()