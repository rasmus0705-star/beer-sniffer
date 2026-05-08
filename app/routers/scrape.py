from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.scrapers.brygshoppen import scrape_brygshoppen
from app.scrapers.agoodcase import scrape_agoodcase
from app.scrapers.beershoppen import scrape_beershoppen
from app.scrapers.bestofbeers import scrape_bestofbeers
from app.services.ingest import ingest_batch

router = APIRouter()

@router.get("/scrape-all")
def scrape_all(db: Session = Depends(get_db)):
    all_items = []
    results = {}

    for name, func in [
        ("brygshoppen", scrape_brygshoppen),
        ("agoodcase", scrape_agoodcase),
        ("beershoppen", scrape_beershoppen),
        ("bestofbeers", scrape_bestofbeers),
    ]:
        try:
            items = func()
            all_items.extend(items)
            results[name] = len(items)
        except Exception as e:
            results[name] = f"fejl: {str(e)}"

    ingest_batch(db, all_items)
    return {"status": "ok", "results": results, "total": len(all_items)}

@router.get("/scrape-brygshoppen")
def scrape(db: Session = Depends(get_db)):
    items = scrape_brygshoppen()
    ingest_batch(db, items)
    return {"status": "ok", "count": len(items)}