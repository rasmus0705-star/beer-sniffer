from fastapi import FastAPI
from app.routers import beers, scrape
from app.services.scheduler import scheduler

app = FastAPI()

app.include_router(beers.router)
app.include_router(scrape.router)


@app.on_event("startup")
def start_scheduler():
    scheduler.start()
    print("🚀 Scheduler started")