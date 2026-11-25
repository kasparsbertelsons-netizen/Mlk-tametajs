@echo off
setlocal
cd /d "%~dp0"
title MLK Tamesanas Agents - lokala versija

echo ============================================================
echo  MLK Tamesanas Agents - LOKALA palaisana (tikai 127.0.0.1)
echo  PDF apstrade notiek tikai uz so datora. Nekas netiek sutits uz internetu.
echo  Internets vajadzigs TIKAI atkaribu instalesanai pirmaja reize vai pec "--update".
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

REM Fiksets paligs: parbauda atkaribas bez interneta, instale tikai ja vajag, un palaiz Streamlit uz 127.0.0.1
REM (--server.address 127.0.0.1, --browser.gatherUsageStats false). Ievade netiek likta komandrinda.
set "UPDATE="
if /i "%~1"=="--update" set "UPDATE=--update"
".venv\Scripts\python.exe" tools\local_setup.py start %UPDATE%
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

:end
echo.
pause
exit /b %EXITCODE%
