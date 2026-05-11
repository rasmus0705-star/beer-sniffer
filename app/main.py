from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from app.routers import beers, scrape
from app.services.scheduler import scheduler

app = FastAPI()

# GZip komprimering — reducerer datamængden der sendes til browseren
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(beers.router)
app.include_router(scrape.router)

@app.on_event("startup")
def start_scheduler():
    scheduler.start()
    print("🚀 Scheduler started")