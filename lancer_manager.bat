@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title DECA Manager
cd /d "%~dp0"

echo.
echo  ==========================================
echo   DECA Manager - PSO Tooling SAESB
echo  ==========================================
echo.

REM -- Cherche Python : chemin fixe SAESB en priorite, sinon PATH --
set PYTHON=C:\SafApp\Python\Python3.14-64\python.exe
if not exist "!PYTHON!" (
    where python >nul 2>&1
    if errorlevel 1 (
        echo  [ERREUR] Python introuvable.
        echo  Installe Python 3.10+ depuis https://www.python.org/downloads/
        echo  ou contacte l administrateur.
        pause
        exit /b 1
    )
    set PYTHON=python
)

echo  Python : !PYTHON!
echo.

REM -- Verifie la version Python --
"!PYTHON!" -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo  [ERREUR] Python 3.10 minimum requis.
    "!PYTHON!" --version
    pause
    exit /b 1
)

REM -- Installe / verifie les dependances --
echo  Verification des dependances...
"!PYTHON!" -c "import PyQt6, pandas, openpyxl" >nul 2>&1
if errorlevel 1 (
    echo  [INFO] Installation des dependances (peut prendre 1-2 min)...
    "!PYTHON!" -m pip install --quiet PyQt6 pandas openpyxl
    if errorlevel 1 (
        echo  [ERREUR] Echec installation. Lance manuellement :
        echo  "!PYTHON!" -m pip install PyQt6 pandas openpyxl
        pause
        exit /b 1
    )
    echo  [OK] Dependances installees.
)

echo.
echo  Demarrage de DECA Manager...
"!PYTHON!" deca_manager.py
if errorlevel 1 (
    echo.
    echo  [ERREUR] DECA Manager ferme avec une erreur.
    echo  Relance depuis un terminal pour voir le detail :
    echo  "!PYTHON!" deca_manager.py
    echo.
)

pause
