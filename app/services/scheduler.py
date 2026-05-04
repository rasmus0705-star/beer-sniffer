from apscheduler.schedulers.background import BackgroundScheduler
from app.database import SessionLocal
from app.scrapers.brygshoppen import scrape_brygshoppen
from app.services.ingest import ingest_batch


def run_scraper():
    print("⏱ Running scheduled scrape...")

    db = SessionLocal()

    try:
        items = scrape_brygshoppen()
        ingest_batch(db, items)
        print(f"✅ Scraped {len(items)} beers")
    finally:
        db.close()


scheduler = BackgroundScheduler()
scheduler.add_job(run_scraper, "interval", minutes=30)