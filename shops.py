"""
shops.py — Auto-discovery af butikker fra app/scrapers/.

Hver scraper-fil skal have disse konstanter øverst:
    SHOP_NAME = "Butiksnavn"
    SHOP_URL = "https://butik.dk"
    SHOP_SHIPPING = {"price": 49, "freeOver": 599, "note": "Fragtbeskrivelse"}
    # Sæt SHOP_SHIPPING = None hvis fragt ikke er offentligt tilgængeligt

Nye scrapers opdages automatisk — ingen redigering af denne fil nødvendig.
"""

import ast
import importlib
import os


def discover_shops(scraper_dir=None):
    """Scanner app/scrapers/ og returnerer metadata for alle filer med SHOP_NAME."""
    if scraper_dir is None:
        scraper_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "scrapers")

    shops = []

    for filename in sorted(os.listdir(scraper_dir)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue

        filepath = os.path.join(scraper_dir, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()
        except Exception:
            continue

        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        constants = {}
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in (
                        "SHOP_NAME", "SHOP_URL", "SHOP_SHIPPING"
                    ):
                        try:
                            constants[target.id] = ast.literal_eval(node.value)
                        except (ValueError, TypeError):
                            if target.id == "SHOP_SHIPPING":
                                constants[target.id] = None

        if "SHOP_NAME" not in constants:
            continue

        func_name = None
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("scrape_"):
                func_name = node.name
                break

        if not func_name:
            continue

        module_name = f"app.scrapers.{filename[:-3]}"

        shops.append({
            "name": constants["SHOP_NAME"],
            "module": module_name,
            "function": func_name,
            "url": constants.get("SHOP_URL", ""),
            "shipping": constants.get("SHOP_SHIPPING"),
        })

    return shops


def get_scrapers():
    """Returnerer [(name, scrape_function), ...] klar til build_data.py"""
    shops = discover_shops()
    result = []
    for shop in shops:
        mod = importlib.import_module(shop["module"])
        func = getattr(mod, shop["function"])
        result.append((shop["name"], func))
    return result


def get_shipping_js(shops=None):
    """Genererer SHIPPING JS-objekt til index.html"""
    if shops is None:
        shops = discover_shops()
    lines = []
    for shop in shops:
        s = shop["shipping"]
        if s:
            lines.append(
                f"        '{shop['name']}': "
                f"{{ price: {s['price']}, freeOver: {s['freeOver']}, note: '{s['note']}' }},"
            )
    comment = (
        "        // Butikker uden shipping-info beregner fragt ved checkout\n"
        "        // og falder automatisk tilbage til 'ikke tilgængelig'-visningen."
    )
    return "    const SHIPPING = {\n" + "\n".join(lines) + "\n" + comment + "\n    };"


def get_footer_html(shops=None):
    """Genererer footer-links"""
    if shops is None:
        shops = discover_shops()
    lines = []
    for shop in shops:
        lines.append(
            f'            <a href="{shop["url"]}" target="_blank" '
            f'rel="noopener">{shop["name"]}</a>'
        )
    return "\n".join(lines)


def get_seo_names(shops=None):
    """Returnerer kommasepareret butikliste til SEO-tekst"""
    if shops is None:
        shops = discover_shops()
    names = [s["name"] for s in shops]
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " og " + names[-1]


if __name__ == "__main__":
    shops = discover_shops()
    print(f"Fundet {len(shops)} butikker:\n")
    for s in shops:
        shipping = (
            f"flat {s['shipping']['price']} kr, fri over {s['shipping']['freeOver']} kr"
            if s["shipping"] else "ikke offentlig"
        )
        print(f"  {s['name']:20s} {s['module']:35s} -> {s['function']}()")
        print(f"  {'':20s} {s['url']:35s}   Fragt: {shipping}")
        print()