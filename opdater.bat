@echo off
cd /d C:\Kodning\beer-sniffer
call .venv\Scripts\activate.bat
python build_data.py
git add data.json
git commit -m "Daglig opdatering"
git push
echo.
echo FAERDIG!
pause
