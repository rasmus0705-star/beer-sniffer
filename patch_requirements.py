import shutil
P = "requirements.txt"
shutil.copy(P, P + ".bak")
new_content = """sqlalchemy
psycopg2-binary
requests
python-dotenv
rapidfuzz
openpyxl
"""
with open(P, "w", encoding="utf-8") as f:
    f.write(new_content)
print("OK: requirements.txt beskaaret 10 -> 6 linjer. Backup: requirements.txt.bak")
print("Fjernet: fastapi, uvicorn, apscheduler, beautifulsoup4")
