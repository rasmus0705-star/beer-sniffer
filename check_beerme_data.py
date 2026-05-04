# check_beerme_data.py
import requests
import xml.etree.ElementTree as ET

FEED_URL = "https://www.partner-ads.com/dk/feed_udlaes.php?partnerid=56605&bannerid=74625&feedid=1666"

r = requests.get(FEED_URL, timeout=15)
r.encoding = 'iso-8859-1'
root = ET.fromstring(r.content)

for produkt in root.findall('produkt'):
    name = produkt.findtext('produktnavn') or ''
    if 'westmalle' in name.lower() or 'dubbel' in name.lower():
        print("=== PRODUKT ===")
        for child in produkt:
            if child.text and child.text.strip():
                print(f"  {child.tag}: {child.text.strip()}")
        print()