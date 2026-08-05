# 🛠️ MultiToolApp — Convertisseur & Assembleur

Application desktop (CustomTkinter) regroupant : téléchargement vidéo → MP3/MP4 (yt-dlp), conversion de fichiers multi-formats, assemblage PDF, et édition/annotation de PDF.

## Onglets

| Onglet | Fonctions |
|---|---|
| 📥 Vidéo | Téléchargement d'une URL en MP4 (360p → 1080p) ou MP3 (128/192/320 kbps) |
| 🔄 Convertisseur | Images, vidéo, audio, documents, tableurs, archives |
| 📄 PDF | Fusion de plusieurs PDF, plages de pages, rotation |
| ✏️ Éditeur PDF | Texte, signature, formes, flèches, surlignage, filigrane |

## ✏️ Éditeur PDF

Ouvrez un PDF, choisissez un outil dans la palette, puis cliquez (texte) ou glissez (formes) sur l'aperçu de la page. Ce qui est affiché correspond exactement au rendu final : l'aperçu et l'écriture partagent le même repère de coordonnées.

- **Texte** — police (Helvetica / Times / Courier), taille, couleur, gras, italique, souligné
- **Signature** — tracée à la souris dans une fenêtre dédiée, ou importée depuis une image ; posée dans la zone glissée, fond transparent conservé
- **Formes** — ligne, flèche (pointe orientée automatiquement), rectangle, ellipse, avec couleur de trait, remplissage, épaisseur et opacité
- **Surlignage** — rectangle semi-transparent, opacité plafonnée pour que le texte dessous reste lisible
- **Filigrane** — cochez la case pour apposer un mot (« CONFIDENTIEL » par défaut) en diagonale, centré **sur toutes les pages**. Texte, couleur, taille et intensité réglables.

  Les lettres sont tracées **évidées** : un contour net porte la lisibilité du mot, tandis que l'intérieur, presque transparent, laisse passer le texte du document sans le voiler. Un texte plein, même très pâle, poserait au contraire un voile coloré sur tout ce qu'il recouvre.

  L'aperçu du filigrane est produit par le moteur de rendu lui-même, sur une copie jetable de la page : ce qui est affiché à l'écran est exactement l'image du PDF qui sera écrit.

`↶ Annuler` retire la dernière annotation, `🗑 Tout effacer` les retire toutes. Le fichier source n'est jamais modifié : `💾 Enregistrer sous...` écrit un nouveau PDF (un suffixe `_1`, `_2`… est ajouté si le nom existe déjà).

Les polices utilisées sont les 14 polices standard du format PDF : aucune police n'est embarquée, le fichier reste léger et s'ouvre à l'identique partout.

## Installation (développement)

```bash
cd multi-tool-app
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python main.py
```

**ffmpeg requis** pour la vidéo/audio : téléchargez-le sur https://www.gyan.dev/ffmpeg/builds/ et ajoutez-le au PATH, ou placez `ffmpeg.exe` + `ffprobe.exe` dans un dossier `bin/` (A CRÉE) à la racine du projet (détecté automatiquement, et bundlé par PyInstaller).

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
