@echo off
setlocal
cd /d "%~dp0"
title MLK AD diagnostika - lokala

if not exist ".venv\Scripts\python.exe" (
    echo Vispirms vienreiz palaidiet start_mlk_windows.bat, lai izveidotu vidi .venv.
    pause
    exit /b 1
)
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"

echo ============================================================
echo  MLK AD diagnostika - LOKALA (nekas netiek sutits uz internetu)
echo  Pilns parskats satur PDF saturu: nekopigojiet un nepublicejiet to.
echo ============================================================
echo.

if not "%~1"=="" goto :withargs

set /p "PDFPATH=PDF faila cels (var ievilkt failu so logu un nospiest Enter): "
set "PDFPATH=%PDFPATH:"=%"
if "%PDFPATH%"=="" goto :nopdf
set /p "PAGES=Plana lapa(s), piem. 3 vai 3,5 (Enter = automatiski): "
set /p "CONTROLS=Jusu zinamais modula izmers mm, piem. 12000x4000 (Enter = bez kontroles): "
set /p "SAVE=Saglabat lokalu HTML parskatu mape local_reports? (J/N): "
set /p "SUMM=Paradit sanitizeto kopsavilkumu apskatei (nekas netiek sutits)? (J/N): "

set "ARGS="
if not "%PAGES%"=="" set "ARGS=%ARGS% --page %PAGES%"
if not "%CONTROLS%"=="" set "ARGS=%ARGS% --control %CONTROLS%"
if /i "%SAVE%"=="J" set "ARGS=%ARGS% --html local_reports\diagnostika.html --overwrite"
if /i "%SUMM%"=="J" set "ARGS=%ARGS% --print-summary"

".venv\Scripts\python.exe" -m tools.ad_diagnostics "%PDFPATH%" %ARGS%
goto :end

:withargs
".venv\Scripts\python.exe" -m tools.ad_diagnostics %*
goto :end

:nopdf
echo Nav noradits PDF fails.

:end
echo.
pause
