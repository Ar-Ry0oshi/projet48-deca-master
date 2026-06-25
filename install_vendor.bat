@echo off
cd /d "%~dp0"
echo Installation des librairies dans vendor/...
python -m pip install -r requirements.txt --target=vendor
echo.
echo Termine. Lance l'app avec : lancer.bat
pause
