@echo off
title BeerSniffer - Daglig opdatering
cd /d C:\Kodning\beer-sniffer

echo ============================================================
echo                    BeerSniffer - Opdatering
echo ============================================================
echo.

echo [1/4] Aktiverer Python miljo og korer scrapers...
echo.
python build_data.py
if errorlevel 1 (
    echo.
    echo FEJL: build_data.py fejlede
    pause
    exit /b 1
)

echo.
echo [2/4] Committer aendringer til git...
git add data.json

REM Tjek om der er aendringer at committe
git diff --cached --quiet
if errorlevel 1 (
    echo Aendringer fundet - committer
    git commit -m "Daglig opdatering"
) else (
    echo Ingen aendringer i data.json
    pause
    exit /b 0
)

echo.
echo [3/4] Pusher til GitHub...
git push
if errorlevel 1 (
    echo.
    echo FEJL: git push fejlede - tjek din internetforbindelse og GitHub-status
    pause
    exit /b 1
)

echo.
echo [4/4] FAERDIG!
echo.
echo beersniffer.dk er opdateret om 1-2 minutter.
echo.
pause