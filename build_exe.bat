@echo off
REM Genere l'executable standalone dist\MultiToolApp.exe
REM (ffmpeg de bin\ est embarque automatiquement via build.spec)
cd /d "%~dp0"
if not exist ".venv\Scripts\activate.bat" (
    echo Environnement introuvable. Lancez d'abord install.bat
    pause & exit /b 1
)
call .venv\Scripts\activate.bat
pyinstaller build.spec --noconfirm
if errorlevel 1 (
    echo [ERREUR] Echec du build.
) else (
    echo.
    echo Build termine : dist\MultiToolApp.exe
)
pause
