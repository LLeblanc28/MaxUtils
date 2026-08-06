# 🛠️ MultiToolApp — Convertisseur & Assembleur

Application desktop (CustomTkinter) regroupant : téléchargement vidéo → MP3/MP4 (yt-dlp), conversion de fichiers multi-formats, assemblage PDF, et édition/annotation de PDF.

## Onglets

| Onglet | Fonctions |
|---|---|
| 📥 Vidéo | Téléchargement d'une URL en MP4 (360p → 1080p) ou MP3 (128/192/320 kbps), playlists, sous-titres, extraction d'un passage |
| 🔄 Convertisseur | Images, vidéo, audio, documents, tableurs, archives ; redimensionnement et compression d'images |
| 📄 Fusion PDF | Fusion de plusieurs PDF, plages de pages, rotation |
| ✏️ Éditeur PDF | Texte, signature, formes, flèches, surlignage, filigrane |
| 🧰 Outils PDF | Découpe/extraction de pages, compression, protection et déverrouillage par mot de passe |

Les fichiers peuvent être **glissés-déposés** dans les onglets Convertisseur, Fusion, Éditeur et Outils. L'interface est disponible en **français et en anglais** (Paramètres → Langue ; le changement s'applique au redémarrage).

## 📥 Vidéo

- **Playlists** — cochez « Toute la playlist » pour télécharger la liste entière. Chaque fichier est préfixé de son numéro d'ordre, ce qui préserve l'ordre et évite qu'un titre en double n'en écrase un autre.
- **Sous-titres** — français, anglais, espagnol, allemand ou italien. Les sous-titres générés automatiquement sont inclus, faute de quoi l'option resterait sans effet sur la majorité des vidéos.
- **Extrait** — indiquez un début et une fin (`1:20`, `01:02:03`) pour ne récupérer qu'un passage. La découpe est alignée sur les images-clés, sans quoi l'extrait déborderait de plusieurs secondes.
- **Mise à jour de yt-dlp** — bouton dans les paramètres. C'est la seule dépendance qui se périme vite : les plateformes changent leurs API régulièrement, et une version figée finit par ne plus rien télécharger.

## 🧰 Outils PDF

Un seul document en entrée, trois opérations :

- **Découper / extraire** — un fichier unique contenant les pages choisies (`1-3,7`), ou un fichier par page.
- **Compresser** — trois niveaux. Le résultat affiche les tailles avant/après, et signale honnêtement l'absence de gain sur un PDF déjà optimisé.
- **Protéger / déverrouiller** — chiffrement **AES-256**, avec ou sans autorisation d'impression. Le chiffrement passe par PyMuPDF : l'AES-256 de pypdf exigerait le paquet `cryptography`, et son repli sans cette dépendance est le RC4, un algorithme cassé — inacceptable pour une fonction censée protéger un document.

Un PDF ainsi protégé ne peut pas être fusionné tant qu'il n'est pas déverrouillé ; l'onglet Fusion le signale explicitement plutôt que d'échouer sur une erreur technique.

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
