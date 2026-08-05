"""Génération d'une image de signature à partir de tracés à la souris.

Séparé de l'UI pour rester testable : la fenêtre de dessin
(`ui/signature_dialog.py`) ne fait que collecter des points et appelle
`render_signature()` pour produire le PNG.
"""

import tempfile
import uuid
from pathlib import Path

# Dossier de travail des signatures de la session. Sous le dossier temporaire
# du système : nettoyé par l'OS, et jamais dans les documents de l'utilisateur.
SIGNATURE_DIR = Path(tempfile.gettempdir()) / "multitoolapp_signatures"

Stroke = list[tuple[float, float]]


def render_signature(
    strokes: list[Stroke],
    output_path: str | None = None,
    color: tuple[float, float, float] = (0.05, 0.05, 0.35),
    width: int = 3,
    padding: int = 12,
) -> str:
    """Convertit des tracés en PNG à fond transparent, recadré sur le contenu.

    Args:
        strokes: liste de tracés, chacun étant une suite de points (x, y) en
            coordonnées écran.
        output_path: fichier cible ; un nom unique est généré si omis.
        color: couleur de l'encre, en RGB normalisé 0-1.
        width: épaisseur du trait en pixels.
        padding: marge transparente conservée autour du tracé.

    Returns:
        Chemin du PNG généré.

    Raises:
        ValueError: si aucun tracé exploitable n'est fourni.
    """
    from PIL import Image, ImageDraw

    points = [p for stroke in strokes for p in stroke]
    if not points:
        raise ValueError("Aucun tracé : dessinez votre signature avant de valider.")

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    # Un point isolé ou un trait parfaitement horizontal donnerait une image de
    # largeur ou hauteur nulle : on garantit au moins 1 pixel utile.
    img_w = int(max_x - min_x) + 2 * padding + 1
    img_h = int(max_y - min_y) + 2 * padding + 1

    ink = tuple(int(round(c * 255)) for c in color) + (255,)
    image = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    for stroke in strokes:
        shifted = [(x - min_x + padding, y - min_y + padding) for x, y in stroke]
        if len(shifted) == 1:
            # Un simple clic : PIL.line ne trace rien avec un seul point.
            x, y = shifted[0]
            r = width / 2
            draw.ellipse([x - r, y - r, x + r, y + r], fill=ink)
        else:
            draw.line(shifted, fill=ink, width=width, joint="curve")

    if output_path is None:
        SIGNATURE_DIR.mkdir(parents=True, exist_ok=True)
        output_path = str(SIGNATURE_DIR / f"signature_{uuid.uuid4().hex[:8]}.png")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return str(output_path)
