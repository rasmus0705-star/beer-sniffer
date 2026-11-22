import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()
engine = create_engine(os.environ["DB_URL"])

with engine.connect() as conn:
    r1 = conn.execute(text("DELETE FROM prices WHERE shop_name = 'Olle Glad'"))
    conn.commit()
    print(f"Slettet {r1.rowcount} prisrækker med shop_name='Olle Glad'")
