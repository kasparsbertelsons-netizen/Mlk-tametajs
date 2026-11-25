@echo off
setlocal
cd /d "%~dp0"
title MLK AD diagnostika - lokala

if not exist ".venv\Scripts\python.exe" goto :notready
".venv\Scripts\python.exe" tools\local_setup.py check >nul 2>nul
if errorlevel 1 goto :notready

echo ============================================================
echo  MLK AD diagnostika - LOKALA (nekas netiek sutits uz internetu)
echo  Pilns parskats satur PDF saturu: nekopigojiet un nepublicejiet to.
echo ============================================================
echo.

REM Fiksets Python rikks. Visu ievadi (PDF cels, lapas, kontrolizmeri, saglabasana) pats pieprasa un valide Python;
REM nekas netiek likts komandrinda. Ja PDF fails ievilkts uz so .bat, tas tiek nodots ka viens atsevisks arguments.
".venv\Scripts\python.exe" -m tools.ad_diagnostics --interactive "%~1"
goto :end

:notready
echo Vide vel nav sagatavota. Vispirms palaidiet start_mlk_windows.bat vienu reizi.

:end
echo.
pause
