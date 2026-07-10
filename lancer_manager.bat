@echo off
title DECA Manager
cd /d "%~dp0"

echo.
echo  ==========================================
echo   DECA Manager - PSO Tooling SAESB
echo  ==========================================
echo.

set PYTHON=C:\SafApp\Python\Python3.14-64\python.exe
if not exist "%PYTHON%" set PYTHON=python

echo  Verification des dependances...
"%PYTHON%" -c "import PyQt6, pandas, openpyxl, streamlit" >nul 2>&1
if errorlevel 1 (
    echo  Installation en cours...
    "%PYTHON%" -m pip install --quiet PyQt6 pandas openpyxl streamlit
)

echo  Demarrage...
start "" "%PYTHON%" deca_manager.py
