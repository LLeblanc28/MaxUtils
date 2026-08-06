"""Mise à jour de yt-dlp depuis l'application.

yt-dlp est le seul paquet du projet qui se périme vite : les plateformes
vidéo modifient leurs API régulièrement, et une version figée cesse de
fonctionner au bout de quelques semaines. Ce module permet de le mettre à
jour sans passer par un terminal.
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request

PYPI_PACKAGE = "yt-dlp"
UPDATE_TIMEOUT = 180  # secondes : installation depuis PyPI, réseau compris

# Dépôt consulté pour savoir si une version plus récente de l'application
# existe. Seule la dernière release publiée est lue : aucune donnée n'est
# envoyée, la requête ne contient que l'adresse.
RELEASES_URL = "https://api.github.com/repos/LLeblanc28/MaxUtils/releases/latest"
RELEASES_PAGE = "https://github.com/LLeblanc28/MaxUtils/releases/latest"
CHECK_TIMEOUT = 10  # secondes


def parse_version(text: str) -> tuple[int, ...]:
    """Convertit « v1.2.3 » en (1, 2, 3), pour comparer deux versions.

    Les segments non numériques sont ignorés : une étiquette du type
    « v1.2.3-beta » se compare donc sur ses seuls nombres, ce qui suffit à
    répondre à la seule question posée — y a-t-il plus récent ?
    """
    numbers: list[int] = []
    for chunk in text.strip().lstrip("vV").replace("-", ".").split("."):
        if chunk.isdigit():
            numbers.append(int(chunk))
        else:
            break
    return tuple(numbers)


def check_app_update(current: str) -> tuple[bool, str]:
    """Interroge GitHub pour savoir si une version plus récente est publiée.

    Args:
        current: version de l'application en cours d'exécution.

    Returns:
        (mise à jour disponible, message destiné à l'utilisateur). Aucun appel
        ne lève : sans réseau, l'utilisateur doit voir une explication, pas
        une trace d'erreur.
    """
    request = urllib.request.Request(
        RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "MultiToolApp"},
    )
    try:
        with urllib.request.urlopen(request, timeout=CHECK_TIMEOUT) as response:  # nosec B310
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False, "Aucune version n'a encore été publiée sur GitHub."
        return False, f"Vérification impossible (erreur {e.code})."
    except (urllib.error.URLError, TimeoutError):
        return False, "Vérification impossible : aucune connexion à Internet."
    except (ValueError, OSError) as e:
        return False, f"Vérification impossible : {e}"

    latest = str(payload.get("tag_name") or "").strip()
    if not latest:
        return False, "Aucune version n'a encore été publiée sur GitHub."

    if parse_version(latest) > parse_version(current):
        return True, f"Version {latest} disponible (vous avez la {current}) : {RELEASES_PAGE}"
    return False, f"Vous utilisez la dernière version ({current})."


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
