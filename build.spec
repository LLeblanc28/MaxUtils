# -*- mode: python ; coding: utf-8 -*-
"""Config PyInstaller pour MultiToolApp.

Bundle ffmpeg/ffprobe : placez ffmpeg.exe et ffprobe.exe dans un dossier ./bin
avant le build. Commande : pyinstaller build.spec
"""

import os

binaries = []
for exe in ("ffmpeg.exe", "ffprobe.exe", "ffmpeg", "ffprobe"):
    p = os.path.join("bin", exe)
    if os.path.isfile(p):
        binaries.append((p, "bin"))

datas = []
if os.path.isfile(os.path.join("assets", "icon.ico")):
    datas.append((os.path.join("assets", "icon.ico"), "assets"))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=["PIL._tkinter_finder"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MultiToolApp",
    debug=False,
    strip=False,
    upx=True,
    console=False,
    icon=os.path.join("assets", "icon.ico") if os.path.isfile(os.path.join("assets", "icon.ico")) else None,
)
