import requests
import xml.etree.ElementTree as ET

FEED_URL = "https://www.partner-ads.com/dk/feed_udlaes.php?partnerid=56605&bannerid=74625&feedid=1666"

r = requests.get(FEED_URL, timeout=15)
r.encoding = 'iso-8859-1'
root = ET.fromstring(r.content)

for produkt in root.findall('produkt'):
    name = produkt.findtext('produktnavn') or ''
    category = produkt.findtext('kategorinavn') or ''
    if 'bundle' in name.lower() or 'barrel' in name.lower() or 'pakke' in name.lower():
        print(f"Navn: {name}")
        print(f"Kategori: {category}")
        print()