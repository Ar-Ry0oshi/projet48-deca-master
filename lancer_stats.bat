@echo off
cd /d "%~dp0"

set PYTHON=C:\SafApp\Python\Python3.14-64\python.exe
if not exist "%PYTHON%" set PYTHON=python

"%PYTHON%" -c "import PyQt6, pandas, openpyxl, matplotlib" >nul 2>&1
if errorlevel 1 (
    echo  Installation des dependances...
    "%PYTHON%" -m pip install --quiet PyQt6 pandas openpyxl matplotlib
    echo  Demarrage DECA Stats...
    start "" "%PYTHON%" stats_app.py
) else (
    wscript "%~dp0DECA Stats.vbs"
)
