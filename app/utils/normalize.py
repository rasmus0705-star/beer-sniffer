import re


def normalize_name(name: str) -> str:
    if not name:
        return ""

    name = name.lower()

    # Bevar danske bogstaver ved at erstatte dem med ascii-ækvivalenter
    name = name.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    name = name.replace("é", "e").replace("è", "e").replace("ê", "e")
    name = name.replace("á", "a").replace("à", "a").replace("â", "a")
    name = name.replace("ü", "u").replace("ö", "o").replace("ä", "a")

    # Fjern volumen og alkohol
    name = re.sub(r"\d+[.,]?\d*\s?(cl|ml|l)\b\.?", "", name)
    name = re.sub(r"\d+[.,]\d+\s?%", "", name)
    name = re.sub(r"\d+\s?%", "", name)

    # Fjern bindestreger og stjerner som separatorer
    name = re.sub(r"\s*[-–*]\s*", " ", name)

    # Fjern beskrivende nationalitetsord
    name = re.sub(r"\b(belgisk|dansk|tysk|engelsk|hollandsk|belgian|german|dutch)\b", "", name)

    # Fjern specialtegn
    name = re.sub(r"[^a-z0-9\s]", "", name)

    # Fjern ekstra mellemrum
    name = re.sub(r"\s+", " ", name).strip()

    return name