@echo off
title DECA_Master — Lanceur
cd /d "%~dp0"

echo.
echo  ==========================================
echo   DECA_Master — PSO Tooling SAESB
echo  ==========================================
echo.

REM -- Vérifie que Python est accessible --
where python >nul 2>&1
if errorlevel 1 (
    echo  [ERREUR] Python introuvable dans le PATH.
    echo  Contacte l'administrateur.
    pause
    exit /b 1
)

REM -- Vérifie que streamlit est installé --
python -m streamlit --version >nul 2>&1
if errorlevel 1 (
    echo  [ERREUR] Streamlit non installé.
    echo  Lance : pip install streamlit
    pause
    exit /b 1
)

REM -- Lance Streamlit dans cette fenêtre (logs visibles) --
echo  Demarrage de l'application...
echo  Ferme cette fenetre pour arreter le serveur.
echo.
start "" msedge "http://localhost:8501"

python -m streamlit run app.py --server.headless true --browser.gatherUsageStats false

pause
