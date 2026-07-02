"""
generate_sitemap.py — Genererer sitemap.xml med forsiden + alle øl-sider.

Kør EFTER data.json er bygget (dvs. efter build_data.py), så listen af
slugs er opdateret. Overskriver sitemap.xml fuldstændigt hver gang —
det er en maskinlæst fil, så det er trygt (ingen manuel redigering at miste).

Kør fra roden af dit projekt:
    python generate_sitemap.py
"""

import json
from datetime import datetime, timezone

SITE_URL = "https://www.beersniffer.dk"


def main():
    with open("data.json", encoding="utf-8") as f:
        data = json.load(f)

    beers = [b for b in data.get("beers", []) if b.get("slug")]
    skipped = len(data.get("beers", [])) - len(beers)
    if skipped:
        print(f"⚠️ {skipped} øl har ingen slug og udelades af sitemap.")

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    static_pages = [
        ("", "1.0", "daily"),           # forsiden
        ("om.html", "0.4", "monthly"),
        ("stats.html", "0.3", "weekly"),
    ]

    urls = []
    for path, priority, changefreq in static_pages:
        urls.append(f"""  <url>
    <loc>{SITE_URL}/{path}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>{priority}</priority>
  </url>""")

    for beer in beers:
        slug = beer["slug"]
        urls.append(f"""  <url>
    <loc>{SITE_URL}/ol/{slug}/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.6</priority>
  </url>""")

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )

    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap)

    print(f"✅ sitemap.xml skrevet med {len(urls)} URL'er (1 forside + {len(static_pages)-1} statiske + {len(beers)} øl-sider).")


if __name__ == "__main__":
    main()