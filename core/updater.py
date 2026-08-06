"""Mise à jour de yt-dlp depuis l'application.

yt-dlp est le seul paquet du projet qui se périme vite : les plateformes
vidéo modifient leurs API régulièrement, et une version figée cesse de
fonctionner au bout de quelques semaines. Ce module permet de le mettre à
jour sans passer par un terminal.
"""

import subprocess
import sys

PYPI_PACKAGE = "yt-dlp"
UPDATE_TIMEOUT = 180  # secondes : installation depuis PyPI, réseau compris


def current_version() -> str:
    """Version de yt-dlp actuellement chargée, ou « inconnue »."""
    try:
        import yt_dlp

        return yt_dlp.version.__version__
    except Exception:
        return "inconnue"


def is_frozen() -> bool:
    """Indique si l'application tourne depuis un exécutable PyInstaller.

    Dans ce cas les paquets sont figés dans le binaire : pip n'est pas
    disponible et une mise à jour est impossible sans reconstruire l'exe.
    """
    return getattr(sys, "frozen", False)


def update_yt_dlp() -> tuple[bool, str]:
    """Met à jour yt-dlp via pip, dans l'interpréteur courant.

    Returns:
        (succès, message destiné à l'utilisateur). Aucun appel ne lève :
        l'appelant affiche simplement le message dans le journal.
    """
    before = current_version()

    if is_frozen():
        return False, (
            "Mise à jour impossible depuis la version exécutable (.exe) : "
            "les dépendances y sont figées. Téléchargez une version plus "
            "récente de l'application, ou lancez-la depuis les sources."
        )

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", PYPI_PACKAGE],
            capture_output=True, text=True, timeout=UPDATE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return False, "Mise à jour interrompue : délai dépassé. Vérifiez votre connexion."
    except OSError as e:
        return False, f"Mise à jour impossible : {e}"

    if proc.returncode != 0:
        return False, f"Échec de la mise à jour : {proc.stderr.strip()[-300:]}"

    if "Successfully installed" not in proc.stdout:
        return True, f"yt-dlp est déjà à jour (version {before})."
    return True, (
        f"yt-dlp mis à jour depuis la version {before}. "
        "Redémarrez l'application pour utiliser la nouvelle version."
    )
