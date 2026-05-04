import re


def normalize_name(name: str):
    if not name:
        return ""

    name = name.lower()

    # fjern volumen (33cl, 50cl osv.)
    name = re.sub(r"\d+\s?(cl|ml|l)", "", name)

    # fjern alkohol %
    name = re.sub(r"\d+([.,]\d+)?\s?%", "", name)

    # erstat komma med punktum
    name = name.replace(",", ".")

    # fjern specialtegn
    name = re.sub(r"[^a-z0-9\s]", "", name)

    # fjern ekstra mellemrum
    name = re.sub(r"\s+", " ", name).strip()

    return name