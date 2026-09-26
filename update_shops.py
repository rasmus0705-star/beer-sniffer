"""
update_shops.py — Opdaterer index.html med butikker fundet af shops.py.

Opdaterer automatisk:
  - SHIPPING JS-objekt
  - Footer-links
  - SEO-tekst med butiknavne

Sikker at køre flere gange — finder og erstatter de eksisterende blokke.
"""

import re
from shops import discover_shops, get_shipping_js, get_footer_html, get_seo_names

FILE = "index.html"


def update_shipping(content, shops):
    """Erstatter hele SHIPPING-blokken."""
    new_shipping = get_shipping_js(shops)

    # Match fra "const SHIPPING = {" til den afsluttende "};"
    pattern = r"    const SHIPPING = \{.*?\};"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        content = content[:match.start()] + new_shipping + content[match.end():]
        return content, True
    return content, False


def update_footer(content, shops):
    """Erstatter footer-links mellem kendte ankerpunkter."""
    new_footer = get_footer_html(shops)

    # Footer-links ligger mellem "Butikker vi sammenligner" (eller første <a href>
    # i footer-col) og </div> for den kolonne.
    # Vi finder blokken af <a href="https://..."> links i footeren
    pattern = (
        r'(            <a href="https?://[^"]*" target="_blank" rel="noopener">[^<]+</a>\n)+'
    )

    # Find alle blokke med butiklinks — vi vil have den i footer-sektionen
    matches = list(re.finditer(pattern, content))
    if matches:
        # Tag den sidste match (footer-sektionen, ikke evt. andre steder)
        # Tjek at det indeholder mindst 3 kendte butiknavne
        for match in reversed(matches):
            block = match.group(0)
            known = ["Brygshoppen", "Beershoppen", "Best of Beers", "Drikbeer"]
            if sum(1 for k in known if k in block) >= 2:
                content = content[:match.start()] + new_footer + "\n" + content[match.end():]
                return content, True
    return content, False


def update_seo_text(content, shops):
    """Opdaterer butiknavne i SEO-afsnittet."""
    seo_names = get_seo_names(shops)

    # Mønster: "butikker som X, Y, Z og W – så du"
    pattern = r"butikker som [^–]+ –"
    match = re.search(pattern, content)
    if match:
        new_text = f"butikker som {seo_names} –"
        content = content[:match.start()] + new_text + content[match.end():]
        return content, True
    return content, False


def main():
    shops = discover_shops()
    print(f"🔍 Fundet {len(shops)} butikker i app/scrapers/\n")

    with open(FILE, "r", encoding="utf-8") as f:
        content = f.read()

    changes = 0

    content, ok = update_shipping(content, shops)
    if ok:
        print(f"  ✅ SHIPPING opdateret ({sum(1 for s in shops if s['shipping'])} med fragtinfo)")
        changes += 1
    else:
        print("  ⚠️  Kunne ikke finde SHIPPING-blok")

    content, ok = update_footer(content, shops)
    if ok:
        print(f"  ✅ Footer opdateret ({len(shops)} butikker)")
        changes += 1
    else:
        print("  ⚠️  Kunne ikke finde footer-links")

    content, ok = update_seo_text(content, shops)
    if ok:
        print(f"  ✅ SEO-tekst opdateret")
        changes += 1
    else:
        print("  ⚠️  Kunne ikke finde SEO-tekst")

    if changes > 0:
        with open(FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"\n✅ {changes} blok(ke) opdateret i {FILE}")
    else:
        print(f"\nℹ️ Ingen ændringer i {FILE}")


if __name__ == "__main__":
    main()