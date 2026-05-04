from selenium import webdriver
from selenium.webdriver.edge.options import Options
from bs4 import BeautifulSoup
import re
import time
from app.utils.detect_type import detect_type


def scrape_belgiskbryg():
    items = []
    seen_urls = set()

    skip_keywords = [
        "glas", "glass", "krus", "opener", "trøje", "t-shirt",
        "cap", "hat", "gave", "gavekort", "merchandise", "sodavand",
        "juice", "spiritus", "whisky", "gin", "rom", "vin", "wine",
        "snack", "chips", "tilbehør", "chokolade", "chocolate",
        "fustage", "fadøl", "keg", "anker", "pant", "bog", "bøger"
    ]

    categories = [2, 4, 5, 6, 7, 8, 10]

    options = Options()
    options.add_argument('--headless')
    driver = webdriver.Edge(options=options)

    try:
        for cat_id in categories:
            for page in range(1, 10):
                url = f"https://belgiskbryg.dk/index.php?id_category={cat_id}&controller=category&p={page}"
                driver.get(url)
                time.sleep(2)

                soup = BeautifulSoup(driver.page_source, 'html.parser')
                products = soup.select('.product-miniature')

                if not products:
                    break

                for product in products:
                    name_el = product.select_one('.product-title')
                    if not name_el:
                        continue
                    name = name_el.text.strip()

                    if not name:
                        continue

                    if any(kw in name.lower() for kw in skip_keywords):
                        continue

                    # URL
                    link_el = product.select_one('a.product-thumbnail')
                    product_url = link_el['href'] if link_el else ''

                    # Skip dubletter
                    if product_url in seen_urls:
                        continue
                    seen_urls.add(product_url)

                    # Pris
                    price_el = product.select_one('.price')
                    if not price_el:
                        continue
                    try:
                        price_text = price_el.text.strip()
                        price = float(price_text.replace('kr.', '').replace('.', '').replace(',', '.').strip())
                    except:
                        continue

                    if price <= 0:
                        continue

                    # Billede
                    img_el = product.select_one('img')
                    image = img_el['src'] if img_el else None
                    if image:
                        image = image.replace('home_default', 'large_default')

                    # Volumen fra navn
                    volume = None
                    vol_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(cl|ml|l)\.?', name.lower())
                    if vol_match:
                        val = float(vol_match.group(1).replace(',', '.'))
                        unit = vol_match.group(2)
                        if unit == 'l':
                            val = val * 100
                        elif unit == 'ml':
                            val = val / 10
                        if val > 75:
                            continue
                        volume = val

                    # ABV fra navn
                    abv = None
                    abv_match = re.search(r'(\d+[.,]\d+)\s*%', name)
                    if abv_match:
                        abv = float(abv_match.group(1).replace(',', '.'))

                    is_smagekasse = any(kw in name.lower() for kw in [
                        "smagekasse", "smagesæt", "mix", "bundle", "pakke", "månedsposen"
                    ]) or bool(re.search(r'\d+\s*stk', name.lower()))

                    item = {
                        "name": name,
                        "price": price,
                        "old_price": None,
                        "discount_pct": None,
                        "url": product_url,
                        "shop_name": "Belgisk Bryg",
                        "volume_cl": volume,
                        "abv": abv,
                        "image": image,
                        "type": detect_type(name),
                        "brewery": None,
                        "category": "smagekasse" if is_smagekasse else "øl",
                    }

                    items.append(item)

                print(f"📦 Kategori {cat_id} side {page}: {len(products)} produkter hentet")

                if len(products) < 20:
                    break

    finally:
        driver.quit()

    print(f"📦 Belgisk Bryg total: {len(items)} produkter")
    return items