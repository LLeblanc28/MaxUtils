"""Module de sécurité centralisé : validation d'URL, de chemins et de fichiers.

Toutes les données provenant d'une source externe (URL utilisateur, titre de
vidéo récupéré en ligne, entrée d'archive, configuration sur disque) doivent
être validées par une des fonctions de ce module avant d'être utilisées pour
construire un chemin de fichier ou d'être passées à une bibliothèque tierce.
"""

import ipaddress
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_URL_SCHEMES = {"http", "https"}
# "0.0.0.0" est ici un hôte à bloquer dans une URL entrante (SSRF), pas une
# adresse de bind réseau : bandit B104 est un faux positif sur cette ligne.
BLOCKED_HOSTNAMES = {"localhost", "0.0.0.0", "::1"}  # nosec B104
MAX_URL_LENGTH = 2048

DEFAULT_MAX_FILE_SIZE = 5 * 1024**3  # 5 Go

# Signatures (magic bytes) fiables en tête de fichier. Les conteneurs dont la
# signature n'est pas à un offset fixe (mp4, mp3, mkv...) ne sont pas couverts
# ici : ils restent validés par ffmpeg, qui refuse ce qu'il ne sait pas décoder.
_FILE_SIGNATURES: dict[str, list[bytes]] = {
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".bmp": [b"BM"],
    ".tiff": [b"II*\x00", b"MM\x00*"],
    ".tif": [b"II*\x00", b"MM\x00*"],
    ".pdf": [b"%PDF-"],
    ".zip": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
    ".7z": [b"7z\xbc\xaf\x27\x1c"],
    # Valeur non utilisée directement : le WEBP a une signature à deux offsets
    # (RIFF...WEBP), traitée par la branche dédiée ci-dessous. La présence de
    # cette clé sert uniquement à ne pas court-circuiter vers `return True`.
    ".webp": [b"RIFF"],
}


class SecurityError(Exception):
    """Levée quand une entrée échoue à une validation de sécurité.

    Distincte des erreurs fonctionnelles (RuntimeError, ValueError) pour que
    l'UI puisse afficher un message dédié plutôt qu'un échec générique.
    """


def validate_url(url: str) -> None:
    """Valide qu'une URL est un lien http(s) public, avant de la passer à yt-dlp.

    Bloque les schémas non-http(s) (ex: file://), les hôtes locaux et les
    adresses IP privées/loopback/link-local (ex: 127.0.0.1, 169.254.169.254,
    192.168.x.x) données littéralement dans l'URL.

    Raises:
        SecurityError: si l'URL est absente, malformée ou pointe vers une
            ressource locale/interne.
    """
    if not url or not isinstance(url, str):
        raise SecurityError("URL vide ou invalide.")
    url = url.strip()
    if len(url) > MAX_URL_LENGTH:
        raise SecurityError("URL trop longue.")

    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_URL_SCHEMES:
        raise SecurityError(
            f"Protocole non autorisé ({parsed.scheme or 'aucun'}). Seuls http/https sont acceptés."
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise SecurityError("URL sans nom d'hôte valide.")
    if hostname in BLOCKED_HOSTNAMES:
        raise SecurityError("Accès aux hôtes locaux interdit.")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        return  # nom de domaine : résolu et contacté par yt-dlp, pas ici
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_unspecified or ip.is_multicast:
        raise SecurityError("Accès aux adresses IP internes/privées interdit.")


def sanitize_filename(name: str, max_length: int = 200, fallback: str = "fichier") -> str:
    """Nettoie un nom destiné à devenir un nom de fichier.

    Ne conserve que les caractères alphanumériques (unicode inclus), espaces,
    points, tirets et underscores — élimine séparateurs de chemin, ".." et
    caractères de contrôle.
    """
    safe = "".join(c for c in name if c.isalnum() or c in " ._-").strip()
    safe = safe.lstrip(".")  # évite les fichiers cachés et les ".."
    if not safe:
        safe = fallback
    return safe[:max_length]


def ensure_within_directory(path: str, base_dir: str) -> Path:
    """Vérifie qu'un chemin résolu reste bien à l'intérieur de `base_dir`.

    Returns:
        Le chemin résolu (Path), s'il est valide.

    Raises:
        SecurityError: si `path` s'échappe de `base_dir` (path traversal / Zip Slip).
    """
    base = Path(base_dir).resolve()
    target = Path(path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise SecurityError(f"Chemin hors du dossier autorisé : {target}") from None
    return target


def check_file_size(path: str, max_bytes: int = DEFAULT_MAX_FILE_SIZE) -> None:
    """Refuse un fichier dépassant `max_bytes`, pour limiter les risques de DoS.

    Raises:
        SecurityError: si le fichier dépasse la taille maximale autorisée.
    """
    size = Path(path).stat().st_size
    if size > max_bytes:
        raise SecurityError(
            f"Fichier trop volumineux ({size / 1024**2:.0f} Mo, max {max_bytes / 1024**2:.0f} Mo)."
        )


def verify_file_signature(path: str, expected_ext: str | None = None) -> bool:
    """Vérifie que l'en-tête binaire du fichier correspond à son extension.

    Formats sans signature fiable en tête de fichier (mp4, mp3, mkv...) : la
    fonction retourne True sans vérifier — les rejeter par heuristique
    produirait des faux positifs sur des fichiers valides.
    """
    ext = (expected_ext or Path(path).suffix).lower()
    signatures = _FILE_SIGNATURES.get(ext)
    if not signatures:
        return True
    with open(path, "rb") as f:
        header = f.read(16)
    if ext == ".webp":
        return header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    return any(header.startswith(sig) for sig in signatures)
