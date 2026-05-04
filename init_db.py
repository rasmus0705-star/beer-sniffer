print("STARTING INIT DB")

from app.database import engine, Base

# 🔥 vigtigt: import kun modulet (ikke *!)
import app.models

print("IMPORT DONE")

Base.metadata.create_all(bind=engine)

print("DB initialized")