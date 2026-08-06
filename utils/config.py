"""Constantes globales, chemins par défaut et gestion de la configuration utilisateur.

La configuration est persistée dans un fichier JSON situé dans le dossier
utilisateur (~/.multitoolapp/config.json). Aucune donnée n'est envoyée en ligne.
"""

import json
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "MultiToolApp"
APP_VERSION = "1.0.0"
MIN_WINDOW_SIZE = (800, 600)

CONFIG_DIR = Path.home() / ".multitoolapp"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "theme": "dark",              # dark | light
    "language": "fr",             # fr | en
    "output_dir": str(Path.home() / "Downloads"),
    # Derniers réglages retenus par onglet, sous forme de chaînes simples
    # (libellés de menus, cases cochées). Purement confortable : une valeur
    # absente ou devenue invalide se remplace par le défaut de l'onglet.
    "last_used": {},
}

# Un réglage mémorisé ne doit jamais faire enfler indéfiniment le fichier de
# configuration, ni y faire entrer des données arbitraires.
MAX_REMEMBERED_KEYS = 60
MAX_REMEMBERED_LENGTH = 120

VALID_THEMES = {"dark", "light"}
VALID_LANGUAGES = {"fr", "en"}

# ---------------------------------------------------------------------------
# Formats supportés par le convertisseur
# ---------------------------------------------------------------------------
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif", ".gif", ".heic"}
VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".webm", ".flv"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a"}
DOC_EXTS = {".docx", ".txt"}
SHEET_EXTS = {".csv", ".xlsx"}
ARCHIVE_EXTS = {".zip", ".7z", ".gz", ".tar"}
PDF_EXTS = {".pdf"}

TARGETS_BY_CATEGORY = {
    "image": ["JPG", "PNG", "BMP", "WEBP", "TIFF", "PDF"],
    "video": ["MP4", "AVI", "MKV", "MOV", "MP3", "GIF"],
    "audio": ["MP3", "WAV", "FLAC", "OGG", "AAC"],
    "document": ["PDF"],
    "sheet": ["CSV", "XLSX"],
    "archive": ["ZIP", "EXTRAIRE"],
    "pdf": ["JPG", "PNG"],
}

MP3_BITRATES = ["128", "192", "320"]
MP4_QUALITIES = ["360p", "480p", "720p", "1080p", "Meilleure"]


def resource_path(relative: str) -> str:
    """Retourne le chemin absolu d'une ressource, compatible PyInstaller."""
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, relative)


def get_ffmpeg_path() -> str | None:
    """Localise ffmpeg : bundle PyInstaller, dossier bin/ du projet, puis PATH."""
    exe = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    project_root = Path(__file__).resolve().parent.parent
    candidates = [
        Path(resource_path(os.path.join("bin", exe))),   # bundle PyInstaller
        project_root / "bin" / exe,                      # bin/ du projet
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return shutil.which("ffmpeg")


def _validate_config(data: dict) -> dict:
    """Ne retient que les clés connues, avec des valeurs dans les ensembles autorisés.

    Empêche une clé injectée ou une valeur corrompue dans config.json d'atteindre
    le reste de l'application (M-04).
    """
    result = dict(DEFAULT_CONFIG)
    if not isinstance(data, dict):
        return result
    if data.get("theme") in VALID_THEMES:
        result["theme"] = data["theme"]
    if data.get("language") in VALID_LANGUAGES:
        result["language"] = data["language"]
    output_dir = data.get("output_dir")
    if isinstance(output_dir, str) and output_dir.strip():
        result["output_dir"] = output_dir
    result["last_used"] = _validate_last_used(data.get("last_used"))
    return result


def _validate_last_used(data) -> dict:
    """Ne retient que des couples chaîne → chaîne, bornés en nombre et en taille.

    Ces valeurs sont réinjectées dans des menus au démarrage : un fichier de
    configuration modifié à la main ne doit pas pouvoir y glisser des objets
    arbitraires ni faire enfler le fichier sans limite.
    """
    if not isinstance(data, dict):
        return {}
    clean: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        if len(key) > MAX_REMEMBERED_LENGTH or len(value) > MAX_REMEMBERED_LENGTH:
            continue
        clean[key] = value
        if len(clean) >= MAX_REMEMBERED_KEYS:
            break
    return clean


def load_config() -> dict:
    """Charge la configuration utilisateur, avec valeurs par défaut."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _validate_config(data)
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    """Sauvegarde la configuration utilisateur sur disque."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
