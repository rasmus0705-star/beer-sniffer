import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

KEY = "655681776425426169815"

def hent_xml(url):
    try:
        r = requests.get(url, timeout=10)
        return ET.fromstring(r.content)
    except Exception as e:
        print(f"Fejl: {e}")
        return None

def dato_format(d):
    return f"{str(d.year)[2:]}-{d.month}-{d.day}"

def vis_saldo():
    url = f"https://www.partner-ads.com/dk/saldo_xml.php?key={KEY}"
    root = hent_xml(url)
    if root is None:
        return
    print("\n💳 SALDO")
    print("─" * 40)
    for item in root.iter():
        if item.text and item.text.strip():
            print(f"  {item.tag}: {item.text.strip()}")

def vis_indtjening():
    url = f"https://www.partner-ads.com/dk/partnerindtjening_xml.php?key={KEY}"
    root = hent_xml(url)
    if root is None:
        return
    print("\n💰 INDTJENING")
    print("─" * 40)
    for item in root.iter():
        if item.text and item.text.strip():
            print(f"  {item.tag}: {item.text.strip()}")

def vis_programmer():
    idag = datetime.now()
    fra = dato_format(idag - timedelta(days=30))
    til = dato_format(idag)
    url = f"https://www.partner-ads.com/dk/programstat_xml.php?key={KEY}&fra={fra}&til={til}"
    root = hent_xml(url)
    if root is None:
        return
    print("\n🏪 BUTIKKER DENNE MÅNED")
    print("─" * 40)
    for item in root:
        navn = item.findtext('program') or item.findtext('navn') or item.findtext('name') or ''
        klik = item.findtext('klik') or item.findtext('clicks') or '0'
        beloeb = item.findtext('beloeb') or item.findtext('amount') or '0'
        if navn:
            print(f"  {navn}: {klik} klik — {beloeb} kr")

def vis_klik():
    url = f"https://www.partner-ads.com/dk/klikoversigt_xml.php?key={KEY}"
    root = hent_xml(url)
    if root is None:
        return
    print("\n🖱️  KLIK SENESTE 40 DAGE")
    print("─" * 40)
    total = 0
    for item in root:
        klik = item.findtext('klik') or item.findtext('clicks') or '0'
        dato = item.findtext('dato') or item.findtext('date') or ''
        salg = item.findtext('salg') or item.findtext('sales') or '0'
        if int(klik) > 0:
            total += int(klik)
            print(f"  {dato}: {klik} klik — {salg} salg")
    print(f"\n  Total: {total} klik")

print("=" * 40)
print("🍺 BEERSNIFFER — PARTNER-ADS DASHBOARD")
print(f"   {datetime.now().strftime('%d-%m-%Y %H:%M')}")
print("=" * 40)

vis_saldo()
vis_indtjening()
vis_programmer()
vis_klik()

print("\n" + "=" * 40)