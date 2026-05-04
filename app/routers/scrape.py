from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.scrapers.brygshoppen import scrape_brygshoppen
from app.services.ingest import ingest_batch

router = APIRouter()


@router.get("/scrape-brygshoppen")
def scrape(db: Session = Depends(get_db)):
    items = scrape_brygshoppen()

    ingest_batch(db, items)

    return {
        "status": "ok",
        "count": len(items)
    }