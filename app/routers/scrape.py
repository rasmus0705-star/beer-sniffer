from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database import get_db
from app.scrapers.brygshoppen import scrape_brygshoppen
from app.scrapers.agoodcase import scrape_agoodcase
from app.scrapers.beershoppen import scrape_beershoppen
from app.scrapers.bestofbeers import scrape_bestofbeers
from app.services.ingest import ingest_batch
import os

router = APIRouter()

@router.get("/test-key")
def test_key():
    expected = os.getenv("SCRAPE_API_KEY")
    return {"key_set": expected is not None, "key_length": len(expected) if expected else 0}

def verify_api_key(x_api_key: str = Header(None)):
    expected = os.getenv("SCRAPE_API_KEY")
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Ugyldig API nøgle")

@router.get("/scrape-all")
def scrape_all(db: Session = Depends(get_db), _: None = Depends(verify_api_key)):
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
def scrape(db: Session = Depends(get_db), _: None = Depends(verify_api_key)):
    items = scrape_brygshoppen()
    ingest_batch(db, items)
    return {"status": "ok", "count": len(items)}