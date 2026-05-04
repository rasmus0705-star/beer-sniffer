def detect_type(name: str) -> str | None:
    if not name:
        return None

    name_lower = name.lower()

    types = [
        # IPA varianter
        ("Double IPA", ["double ipa", "dipa"]),
        ("Imperial IPA", ["imperial ipa", "iiipa"]),
        ("New England IPA", ["new england ipa", "neipa", "hazy ipa"]),
        ("West Coast IPA", ["west coast ipa", "wcipa"]),
        ("Session IPA", ["session ipa"]),
        ("Black IPA", ["black ipa"]),
        ("India Pale Ale (IPA)", ["india pale ale", " ipa"]),

        # Stout varianter
        ("Imperial Stout", ["imperial stout"]),
        ("Pastry Stout", ["pastry stout"]),
        ("Milk Stout", ["milk stout"]),
        ("Oatmeal Stout", ["oatmeal stout"]),
        ("Stout", ["stout"]),

        # Porter
        ("Baltic Porter", ["baltic porter"]),
        ("Porter", ["porter"]),

        # Pale Ale
        ("American Pale Ale", ["american pale ale", "apa"]),
        ("Pale Ale", ["pale ale"]),

        # Belgiske
        ("Quadrupel", ["quadrupel", "quad"]),
        ("Tripel", ["tripel", "triple"]),
        ("Dubbel", ["dubbel", "double"]),
        ("Belgian Blonde", ["belgian blonde"]),
        ("Saison", ["saison", "farmhouse"]),
        ("Lambic", ["lambic", "gueuze"]),
        ("Flanders Red Ale", ["flanders red"]),

        # Wheat / Hvede
        ("Hvedeøl", ["hvedeøl", "weizen", "weisse", "witbier", "witte"]),

        # Sour
        ("Gose", ["gose"]),
        ("Berliner Weisse", ["berliner weisse", "berliner"]),
        ("Fruited Sour", ["fruited sour"]),
        ("Sour", ["sour"]),

        # Lager / Pilsner
        ("Pilsner", ["pilsner", "pilsener", "pils"]),
        ("Lager", ["lager"]),
        ("Kölsch", ["kölsch", "kolsch"]),

        # Ale varianter
        ("Scotch Ale", ["scotch ale"]),
        ("Brown Ale", ["brown ale"]),
        ("Golden Ale", ["golden ale"]),
        ("Strong Ale", ["strong ale"]),
        ("Barley Wine", ["barley wine", "barleywine"]),
        ("Winter Ale", ["winter ale"]),
        ("Blonde Ale", ["blonde ale", "blond ale"]),
        ("Dark Ale", ["dark ale"]),

        # Andet
        ("Bock", ["bock"]),
        ("Frugtøl", ["frugtøl", "fruit beer"]),
        ("Mjød", ["mjød", "mead"]),
        ("Cider", ["cider"]),
    ]

    for type_name, keywords in types:
        if any(kw in name_lower for kw in keywords):
            return type_name

    return None