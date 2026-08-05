@echo off
title Extract 1A/1B
cd /d "%~dp0"

set PYTHON=C:\SafApp\Python\Python3.14-64\python.exe
if not exist "%PYTHON%" set PYTHON=python

echo Lancement extract 1A/1B...
"%PYTHON%" scripts\extract_1a1b.py
pause
