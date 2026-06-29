from selenium import webdriver
from selenium.webdriver.edge.options import Options
from bs4 import BeautifulSoup
import time

options = Options()
options.add_argument('--headless')

driver = webdriver.Edge(options=options)

url = "https://belgiskbryg.dk/index.php?id_category=2&controller=category"
driver.get(url)
time.sleep(3)

soup = BeautifulSoup(driver.page_source, 'html.parser')
products = soup.select('.product-miniature')
print(f"Antal produkter fundet: {len(products)}")

for p in products[:3]:
    name = p.select_one('.product-title')
    price = p.select_one('.price')
    img = p.select_one('img')
    link = p.select_one('a.product-thumbnail')
    print(f"\nNavn: {name.text.strip() if name else 'ingen'}")
    print(f"Pris: {price.text.strip() if price else 'ingen'}")
    print(f"Billede: {img['src'] if img else 'ingen'}")
    print(f"Link: {link['href'] if link else 'ingen'}")

driver.quit()