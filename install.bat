@echo off
REM ============================================================
REM  MultiToolApp - Installation automatique complete (Windows)
REM  - Verifie/installe Python 3.11+ (via winget)
REM  - Cree l'environnement virtuel + dependances
REM  - Telecharge ffmpeg/ffprobe dans .\bin
REM  - Cree un raccourci de lancement
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Installation MultiToolApp
echo.
echo  ============================================
echo   Installation de MultiToolApp
echo  ============================================
echo.

REM --- 1. Python ---------------------------------------------------
echo [1/4] Verification de Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo    Python introuvable. Installation via winget...
    winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
    if errorlevel 1 (
        echo    [ERREUR] Echec winget. Installez Python manuellement : https://www.python.org/downloads/
        echo    IMPORTANT : cochez "Add Python to PATH" pendant l'installation.
        pause & exit /b 1
    )
    echo    Python installe. Rechargement du PATH...
    REM Recharge le PATH sans redemarrer le terminal
    for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USERPATH=%%b"
    set "PATH=%PATH%;!USERPATH!"
    python --version >nul 2>&1
    if errorlevel 1 (
        echo    [INFO] Fermez cette fenetre et relancez install.bat pour terminer.
        pause & exit /b 0
    )
)
for /f "tokens=*" %%v in ('python --version') do echo    OK : %%v

REM --- 2. Environnement virtuel + dependances ----------------------
echo.
echo [2/4] Creation de l'environnement virtuel...
if not exist ".venv" python -m venv .venv
call .venv\Scripts\activate.bat
echo    Installation des dependances (peut prendre quelques minutes)...
python -m pip install --upgrade pip -q
pip install -r requirements.txt -q
if errorlevel 1 (
    echo    [ERREUR] Echec d'installation des dependances.
    pause & exit /b 1
)
echo    OK : dependances installees.

REM --- 3. ffmpeg ---------------------------------------------------
echo.
echo [3/4] Verification de ffmpeg...
if exist "bin\ffmpeg.exe" (
    echo    OK : ffmpeg deja present dans bin\
) else (
    echo    Telechargement de ffmpeg (~90 Mo)...
    if not exist "bin" mkdir bin
    powershell -NoProfile -Command ^
      "$ProgressPreference='SilentlyContinue';" ^
      "Invoke-WebRequest 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile '%TEMP%\ffmpeg.zip';" ^
      "Expand-Archive '%TEMP%\ffmpeg.zip' '%TEMP%\ffmpeg_ext' -Force;" ^
      "$b = Get-ChildItem '%TEMP%\ffmpeg_ext' -Recurse -Filter ffmpeg.exe | Select-Object -First 1;" ^
      "Copy-Item $b.FullName 'bin\';" ^
      "Copy-Item (Join-Path $b.DirectoryName 'ffprobe.exe') 'bin\';" ^
      "Remove-Item '%TEMP%\ffmpeg.zip','%TEMP%\ffmpeg_ext' -Recurse -Force"
    if exist "bin\ffmpeg.exe" (
        echo    OK : ffmpeg installe dans bin\
    ) else (
        echo    [ATTENTION] Echec du telechargement. La conversion video/audio
        echo    ne fonctionnera pas. Telechargez ffmpeg manuellement :
        echo    https://www.gyan.dev/ffmpeg/builds/ et placez ffmpeg.exe + ffprobe.exe dans bin\
    )
)

REM --- 4. Raccourci de lancement -----------------------------------
echo.
echo [4/4] Creation du raccourci sur le Bureau...
powershell -NoProfile -Command ^
  "$ws = New-Object -ComObject WScript.Shell;" ^
  "$s = $ws.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\MultiToolApp.lnk');" ^
  "$s.TargetPath = '%~dp0lancer.bat';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "if (Test-Path '%~dp0assets\icon.ico') { $s.IconLocation = '%~dp0assets\icon.ico' };" ^
  "$s.Save()"
echo    OK : raccourci "MultiToolApp" cree sur le Bureau.

echo.
echo  ============================================
echo   Installation terminee !
echo   Lancez l'application via le raccourci Bureau
echo   ou en double-cliquant sur lancer.bat
echo  ============================================
echo.
pause
