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
}

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


def load_config() -> dict:
    """Charge la configuration utilisateur, avec valeurs par défaut."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {**DEFAULT_CONFIG, **data}
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)


def save_co