from apscheduler.schedulers.background import BackgroundScheduler
from app.database import SessionLocal
from app.scrapers.brygshoppen import scrape_brygshoppen
from app.scrapers.agoodcase import scrape_agoodcase
from app.scrapers.beershoppen import scrape_beershoppen
from app.scrapers.bestofbeers import scrape_bestofbeers
from app.scrapers.oeltanken import scrape_oeltanken
from app.services.ingest import ingest_batch


def run_scraper():
    print("⏱ Kører daglig scraping...")
    db = SessionLocal()
    try:
        all_items = []
        for name, func in [
            ("brygshoppen", scrape_brygshoppen),
            ("agoodcase", scrape_agoodcase),
            ("beershoppen", scrape_beershoppen),
            ("bestofbeers", scrape_bestofbeers),
            ("oeltanken", scrape_oeltanken),
        ]:
            try:
                items = func()
                all_items.extend(items)
                print(f"✅ {name}: {len(items)} øl")
            except Exception as e:
                print(f"❌ {name} fejlede: {e}")
        ingest_batch(db, all_items)
        print(f"✅ Samlet: {len(all_items)} øl gemt")
    finally:
        db.close()



scheduler = BackgroundScheduler()
scheduler.add_job(run_scraper, "cron", hour=6, minute=0, misfire_grace_time=3600)