@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Lancement de DECA Manager...
python deca_manager.py
if errorlevel 1 (
    echo.
    echo ERREUR — PyQt6 manquant ? Lance : pip install PyQt6
    pause
)
