from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from app.database import get_db
from app.scrapers.brygshoppen import scrape_brygshoppen
from app.scrapers.agoodcase import scrape_agoodcase
from app.scrapers.beershoppen import scrape_beershoppen
from app.scrapers.bestofbeers import scrape_bestofbeers
from app.scrapers.oeltanken import scrape_oeltanken
from app.scrapers.beerme import scrape_beerme
from app.services.ingest import ingest_batch
from app.models import Beer, Price, PriceHistory
import os

router = APIRouter()


def verify_api_key(x_api_key: str = Header(None)):
    expected = os.getenv("SCRAPE_API_KEY")
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Ugyldig API nøgle")


# ──────────────────────────────────────────────────────────────────────
# RESET — sletter alle øl og priser, bevarer PriceAlert
# ──────────────────────────────────────────────────────────────────────

@router.post("/reset-beers")
def reset_beers(
    confirm: str = "",
    db: Session = Depends(get_db),
    _: None = Depends(verify_api_key),
):
    """
    Sletter alle Beer, Price og PriceHistory rækker så databasen kan bygges op
    fra scratch med den nye matching-logik. Kræver ?confirm=YES.
    Bevarer PriceAlert.
    """
    if confirm != "YES":
        raise HTTPException(
            status_code=400,
            detail="Tilføj ?confirm=YES for at bekræfte sletning"
        )

    try:
        price_count = db.query(Price).count()
        beer_count = db.query(Beer).count()
        history_count = db.query(PriceHistory).count()

        # Slet i rigtig rækkefølge — først child-tabeller, så parent
        db.query(PriceHistory).delete(synchronize_session=False)
        db.commit()

        db.query(Price).delete(synchronize_session=False)
        db.commit()

        db.query(Beer).delete(synchronize_session=False)
        db.commit()

        # Ryd cache
        try:
            from app.routers.beers import clear_cache
            clear_cache()
        except Exception:
            pass

        return {
            "status": "ok",
            "deleted_history": history_count,
            "deleted_prices": price_count,
            "deleted_beers": beer_count,
            "next_step": "Kald /scrape-all for at genopbygge databasen",
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Reset fejlede: {type(e).__name__}: {str(e)}"
        )


# ──────────────────────────────────────────────────────────────────────
# SCRAPE ENDPOINTS
# ──────────────────────────────────────────────────────────────────────

@router.get("/scrape-all")
def scrape_all(db: Session = Depends(get_db), _: None = Depends(verify_api_key)):
    all_items = []
    results = {}
    for name, func in [
        ("brygshoppen", scrape_brygshoppen),
        ("agoodcase", scrape_agoodcase),
        ("beershoppen", scrape_beershoppen),
        ("bestofbeers", scrape_bestofbeers),
        ("oeltanken", scrape_oeltanken),
        ("beerme", scrape_beerme),
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
def scrape_b(db: Session = Depends(get_db), _: None = Depends(verify_api_key)):
    items = scrape_brygshoppen()
    ingest_batch(db, items)
    return {"status": "ok", "count": len(items)}


@router.get("/scrape-agoodcase")
def scrape_a(db: Session = Depends(get_db), _: None = Depends(verify_api_key)):
    items = scrape_agoodcase()
    ingest_batch(db, items)
    return {"status": "ok", "count": len(items)}


@router.get("/scrape-beershoppen")
def scrape_bs(db: Session = Depends(get_db), _: None = Depends(verify_api_key)):
    items = scrape_beershoppen()
    ingest_batch(db, items)
    return {"status": "ok", "count": len(items)}


@router.get("/scrape-bestofbeers")
def scrape_bob(db: Session = Depends(get_db), _: None = Depends(verify_api_key)):
    items = scrape_bestofbeers()
    ingest_batch(db, items)
    return {"status": "ok", "count": len(items)}


@router.get("/scrape-oeltanken")
def scrape_ot(db: Session = Depends(get_db), _: None = Depends(verify_api_key)):
    items = scrape_oeltanken()
    ingest_batch(db, items)
    return {"status": "ok", "count": len(items)}


@router.get("/scrape-beerme")
def scrape_bm(db: Session = Depends(get_db), _: None = Depends(verify_api_key)):
    items = scrape_beerme()
    ingest_batch(db, items)
    return {"status": "ok", "count": len(items)}