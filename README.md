# 🛠️ MultiToolApp — Convertisseur & Assembleur

Application desktop (CustomTkinter) regroupant : téléchargement vidéo → MP3/MP4 (yt-dlp), conversion de fichiers multi-formats, et assemblage PDF.

## Installation (développement)

```bash
cd multi-tool-app
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python main.py
```

**ffmpeg requis** pour la vidéo/audio : téléchargez-le sur https://www.gyan.dev/ffmpeg/builds/ et ajoutez-le au PATH, ou placez `ffmpeg.exe` + `ffprobe.exe` dans un dossier `bin/` à la racine du projet (détecté automatiquement, et bundlé par PyInstaller).

## Build de l'exécutable

```bash
# Avec bundle ffmpeg : placez ffmpeg.exe/ffprobe.exe dans ./bin d'abord
pyinstaller build.spec
# → dist/MultiToolApp.exe
```

Ou en une ligne (sans bundle ffmpeg) :

```bash
pyinstaller --onefile --windowed --icon=assets/icon.ico --name="MultiToolApp" main.py
```

## Notes

- Toutes les opérations lourdes tournent dans des threads séparés (UI non bloquante).
- La conversion DOCX→PDF (docx2pdf) nécessite Microsoft Word installé (Windows).
- HEIC nécessite `pillow-heif`, 7z nécessite `py7zr` (inclus dans requirements).
- Config utilisateur : `~/.multitoolapp/config.json` (thème, langue, dossier de sortie). 100 % local.
- Ajoutez votre icône dans `assets/icon.ico`.
