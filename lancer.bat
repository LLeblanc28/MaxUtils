@echo off
REM Lance MultiToolApp sans fenetre de console
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Environnement introuvable. Lancez d'abord install.bat
    pause & exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" main.py
