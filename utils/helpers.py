"""Fonctions utilitaires partagées entre les modules."""

import os
import platform
import subprocess
import sys
from pathlib import Path


def open_in_explorer(path: str) -> None:
    """Ouvre un fichier ou dossier avec l'application par défaut du système."""
    if platform.system() == "Windows":
        os.startfile(path)  # type: ignore[attr-defined]
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def human_size(num_bytes: float) -> str:
    """Formate une taille en octets de façon lisible (ex: 12.4 MB)."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def format_duration(seconds: float | None) -> str:
    """Formate une durée en secondes sous forme HH:MM:SS ou MM:SS."""
    if not seconds:
        return "??:??"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def unique_path(path: str | Path) -> Path:
    """Retourne un chemin qui n'écrase pas de fichier existant (suffixe _1, _2...)."""
    p = Path(path)
    if not p.exists():
        return p
    stem, suffix, parent = p.stem, p.suffix, p.parent
    i = 1
    while True:
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def parse_page_ranges(spec: str, max_pages: int) -> list[int]:
    """Convertit une spécification de pages ('1-3,5,7-9') en liste d'index 0-based.

    Args:
        spec: chaîne saisie par l'utilisateur. Vide = toutes les pages.
        max_pages: nombre total de pages du document.

    Returns:
        Liste d'index de pages (0-based), dans l'ordre demandé.

    Raises:
        ValueError: si la spécification est invalide ou hors bornes.
    """
    if not spec.strip():
        return list(range(max_pages))
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            start, end = int(a), int(b)
        else:
            start = end = int(part)
        if start < 1 or end > max_pages or start > end:
            raise ValueError(f"Plage invalide : {part} (1-{max_pages})")
        pages.extend(range(start - 1, end))
    return pages
