@echo off
chcp 65001 > nul
cd /d C:\Kodning\beer-sniffer

echo.
echo ============================================================
echo            BeerSniffer - Daglig Opdatering
echo ============================================================
echo.

REM Aktivér virtual environment
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo FEJL: Kunne ikke aktivere virtual environment
    pause
    exit /b 1
)

REM Kør build_data.py
echo [1/3] Scraper alle butikker og bygger data.json...
echo.
python build_data.py
if errorlevel 1 (
    echo.
    echo FEJL: build_data.py fejlede
    pause
    exit /b 1
)

echo.
echo [2/3] Pusher til GitHub...
git add data.json
git commit -m "Daglig opdatering %date%"
if errorlevel 1 (
    echo.
    echo FEJL: Git commit fejlede - måske ingen ændringer?
    pause
    exit /b 1
)

git push
if errorlevel 1 (
    echo.
    echo FEJL: Git push fejlede
    pause
    exit /b 1
)

echo.
echo [3/3] FÆRDIG!
echo.
echo beersniffer.dk opdateres om 1-2 minutter
echo.
pause