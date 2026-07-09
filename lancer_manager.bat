@echo off
chcp 65001 >nul
title DECA Manager — Lanceur
cd /d "%~dp0"

echo.
echo  ==========================================
echo   DECA Manager — PSO Tooling SAESB
echo  ==========================================
echo.

REM -- Utilise le meme Python que le dashboard Streamlit --
set PYTHON=C:\SafApp\Python\Python3.14-64\python.exe

REM -- Verifie PyQt6 --
"%PYTHON%" -c "import PyQt6" >nul 2>&1
if errorlevel 1 (
    echo  [ERREUR] PyQt6 non installe.
    echo  Lance : "%PYTHON%" -m pip install PyQt6
    pause
    exit /b 1
)

echo  Demarrage de DECA Manager...
"%PYTHON%" deca_manager.py

pause
