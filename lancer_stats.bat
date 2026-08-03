@echo off
title DECA Stats
cd /d "%~dp0"

echo.
echo  ==========================================
echo   DECA Stats - PSO Tooling SAESB
echo  ==========================================
echo.

set PYTHON=C:\SafApp\Python\Python3.14-64\python.exe
if not exist "%PYTHON%" set PYTHON=python

echo  Verification des dependances...
"%PYTHON%" -c "import PyQt6, pandas, openpyxl, matplotlib" >nul 2>&1
if errorlevel 1 (
    echo  Installation en cours...
    "%PYTHON%" -m pip install --quiet PyQt6 pandas openpyxl matplotlib
)

echo  Demarrage DECA Stats...
start "" "%PYTHON%" stats_app.py
