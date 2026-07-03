@echo off
chcp 65001 > nul
cd /d C:\Kodning\beer-sniffer
echo.
echo ============================================================
echo            BeerSniffer - Daglig Opdatering
echo ============================================================
echo.
REM Aktiver virtual environment
call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo FEJL: Kunne ikke aktivere virtual environment
    pause
    exit /b 1
)
REM ---- Tjek om fejlliste.xlsx er laast (Excel aaben) ----
echo [0/4] Tjekker om fejlliste.xlsx er aaben i Excel...
python -c "open('fejlliste.xlsx','a').close()" 2>nul
if errorlevel 1 (
    echo.
    echo ============================================================
    echo  STOP: fejlliste.xlsx ser ud til at vaere aaben i Excel.
    echo  Luk filen i Excel og koer denne bat igen.
    echo ============================================================
    echo.
    pause
    exit /b 1
)
echo    OK - filen er ikke laast.
echo.
REM ---- Koer build_data.py (scraper + facit + data.json) ----
echo [1/4] Scraper alle butikker, anvender facit og bygger data.json...
echo.
python build_data.py
if errorlevel 1 (
    echo.
    echo FEJL: build_data.py fejlede
    pause
    exit /b 1
)
REM ---- Stage alle build-outputs ----
REM data.json      = selve prisdata
REM fejlliste.xlsx = facitliste
REM index.html     = DATA_VERSION cache-stempel (opdateres hvert build)
REM ol/            = individuelle oel-sider med dagens priser
REM sitemap.xml    = regenereres hvert build
echo.
echo [2/4] Tilfoejer build-outputs til git...
git add data.json price_history.json fejlliste.xlsx index.html ol/ sitemap.xml
REM ---- Commit (kun hvis der er aendringer) ----
echo.
echo [3/4] Committer...
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Daglig opdatering %date%"
) else (
    echo    Ingen aendringer at committe - springer commit og push over.
    goto :done
)
if errorlevel 1 (
    echo.
    echo FEJL: Git commit fejlede
    pause
    exit /b 1
)
REM ---- Push ----
echo.
echo [4/4] Pusher til GitHub...
git push
if errorlevel 1 (
    echo.
    echo FEJL: Git push fejlede
    pause
    exit /b 1
)
:done
echo.
echo ============================================================
echo  FAERDIG! beersniffer.dk opdateres om 1-2 minutter.
echo ============================================================
echo.
pause