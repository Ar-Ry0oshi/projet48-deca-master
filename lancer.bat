@echo off
cd /d "%~dp0"

:: Vérifie que Python est disponible
where python >nul 2>&1
if errorlevel 1 (
    echo Python introuvable. Installe Python 3.10+ et relance.
    pause
    exit /b 1
)

:: Lance Streamlit via le vendor local
python -c "import sys; sys.path.insert(0,'vendor'); from streamlit.web import cli; cli.main()" run app.py --server.port 8501 --server.headless false

pause
