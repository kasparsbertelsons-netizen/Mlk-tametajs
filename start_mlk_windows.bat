@echo off
setlocal
cd /d "%~dp0"
title MLK Tamesanas Agents - lokala versija

echo ============================================================
echo  MLK Tamesanas Agents - LOKALA palaisana (tikai 127.0.0.1)
echo  PDF apstrade notiek tikai uz so datora. Nekas netiek sutits uz internetu.
echo ============================================================
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto :nopython

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto :oldpython

if not exist ".venv\Scripts\python.exe" (
    echo Veidoju virtualo vidi .venv - tas notiek tikai pirmaja reize...
    %PY% -m venv .venv
    if errorlevel 1 goto :venvfail
)

echo Parbaudu un instaleju atkaribas. Pirmaja reize vajadzigs internets, lai tas lejupieladetu pakotnes.
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :pipfail

if not defined MLK_PORT set "MLK_PORT=8501"
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"

echo.
echo Palaizu lietotni. Adrese datora parluka: http://127.0.0.1:%MLK_PORT%
echo Lai apturetu, aizveriet so logu vai nospiediet Ctrl+C.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 127.0.0.1 --server.port %MLK_PORT% --server.headless false --browser.gatherUsageStats false
set "EXITCODE=%ERRORLEVEL%"
goto :end

:nopython
echo KLUDA: Python nav atrasts. Instalejiet Python 3.11 vai jaunaku no python.org, instalatora atzimejiet "Add python.exe to PATH" vai "py launcher".
set "EXITCODE=1"
goto :end

:oldpython
echo KLUDA: nepieciesams Python 3.11 vai jaunaks. Instalejiet jaunaku versiju no python.org.
set "EXITCODE=1"
goto :end

:venvfail
echo KLUDA: neizdevas izveidot virtualo vidi .venv. Parbaudiet, vai mape nav tikai lasama.
set "EXITCODE=1"
goto :end

:pipfail
echo KLUDA: neizdevas instalet atkaribas. Parbaudiet interneta savienojumu (vajadzigs tikai instalesanai) un meginiet velreiz.
set "EXITCODE=1"
goto :end

:end
echo.
pause
exit /b %EXITCODE%
