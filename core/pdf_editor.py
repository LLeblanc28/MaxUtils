"""Édition de PDF : ajout de texte, signature, formes et filigrane.

Basé sur PyMuPDF (fitz). Toutes les opérations sont locales : le PDF source
n'est jamais modifié sur place, un nouveau fichier est écrit à la sauvegarde.

Repère de coordonnées : celui de PyMuPDF, en points PDF, origine en haut à
gauche de la page, axe Y vers le bas — identique à celui d'un canvas Tk, ce
qui évite toute inversion entre l'aperçu et le rendu final.
"""

import math
from dataclasses import dataclass, field
from pathlib import Path

from utils.security import check_file_size

# Familles proposées à l'utilisateur → codes des polices PDF standard (base 14),
# déclinés par style. Ces polices sont intégrées à tout lecteur PDF : aucune
# police externe n'est embarquée, le fichier reste léger et portable.
FONT_FAMILIES = {
    "Helvetica": "helv",
    "Times": "tiro",
    "Courier": "cour",
}

_FONT_CODES = {
    ("helv", False, False): "helv",
    ("helv", True, False): "hebo",
    ("helv", False, True): "heit",
    ("helv", True, True): "hebi",
    ("tiro", False, False): "tiro",
    ("tiro", True, False): "tibo",
    ("tiro", False, True): "tiit",
    ("tiro", True, True): "tibi",
    ("cour", False, False): "cour",
    ("cour", True, False): "cobo",
    ("cour", False, True): "coit",
    ("cour", True, True): "cobi",
}

# Couleurs proposées dans l'UI (nom lisible → RGB normalisé 0-1 attendu par fitz)
COLORS = {
    "Noir": (0.0, 0.0, 0.0),
    "Rouge": (0.85, 0.11, 0.11),
    "Bleu": (0.11, 0.33, 0.85),
    "Vert": (0.11, 0.60, 0.20),
    "Orange": (0.95, 0.55, 0.05),
    "Jaune": (0.98, 0.87, 0.10),
    "Blanc": (1.0, 1.0, 1.0),
    "Gris": (0.5, 0.5, 0.5),
}

TOOLS = ("text", "signature", "line", "arrow", "rect", "ellipse", "highlight", "redact")

DEFAULT_WATERMARK_TEXT = "CONFIDENTIEL"

# Le filigrane est tracé en lettres évidées : un contour net (bien lisible) et
# un intérieur presque transparent, pour que le texte du document reste net
# dans le creux des lettres. Un texte plein, même très pâle, poserait au
# contraire un voile coloré sur tout ce qu'il recouvre.
WATERMARK_BORDER_WIDTH = 0.03   # épaisseur du contour, en fraction de la taille
WATERMARK_FILL_RATIO = 0.18     # opacité de l'intérieur, en fraction de celle du contour


def resolve_font(family: str = "helv", bold: bool = False, italic: bool = False) -> str:
    """Retourne le code de police PDF correspondant à une famille et un style.

    Args:
        family: code de famille ("helv", "tiro" ou "cour"). Une valeur inconnue
            retombe sur "helv" plutôt que de faire échouer le rendu.
        bold: texte en gras.
        italic: texte en italique.
    """
    if family not in ("helv", "tiro", "cour"):
        family = "helv"
    return _FONT_CODES[(family, bool(bold), bool(italic))]


@dataclass
class Style:
    """Propriétés visuelles d'une annotation (texte et formes confondus)."""

    family: str = "helv"
    size: float = 12.0
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: tuple[float, float, float] = (0.0, 0.0, 0.0)
    fill: tuple[float, float, float] | None = None
    line_width: float = 1.5
    opacity: float = 1.0

    @property
    def font(self) -> str:
        """Code de police PDF résultant de la famille et du style."""
        return resolve_font(self.family, self.bold, self.italic)


@dataclass
class Annotation:
    """Élément à dessiner sur une page.

    Attributes:
        kind: un des TOOLS.
        page: index de page (0-based).
        x0, y0: point de départ (ou point d'ancrage du texte, sur la ligne de base).
        x1, y1: point d'arrivée (ignoré pour le texte).
        text: contenu, pour kind == "text".
        image_path: fichier image, pour kind == "signature".
        style: propriétés visuelles.
    """

    kind: str
    page: int
    x0: float
    y0: float
    x1: float = 0.0
    y1: float = 0.0
    text: str = ""
    image_path: str = ""
    style: Style = field(default_factory=Style)

    @property
    def rect(self) -> tuple[float, float, float, float]:
        """Rectangle normalisé (x0 <= x1, y0 <= y1) délimité par les deux points."""
        return (
            min(self.x0, self.x1),
            min(self.y0, self.y1),
            max(self.x0, self.x1),
            max(self.y0, self.y1),
        )


@dataclass
class Watermark:
    """Filigrane répété au centre de chaque page (ex. « CONFIDENTIEL »)."""

    enabled: bool = False
    text: str = DEFAULT_WATERMARK_TEXT
    size: float = 60.0
    color: tuple[float, float, float] = (0.85, 0.11, 0.11)
    opacity: float = 0.45   # opacité du contour ; l'intérieur reste bien plus clair
    rotation: float = 45.0


class PdfEditor:
    """Ouvre un PDF, fournit un aperçu de page et applique les annotations.

    Le document source reste inchangé : `save()` écrit un nouveau fichier.
    """

    def __init__(self, path: str) -> None:
        """Ouvre le PDF et refuse les fichiers trop volumineux ou protégés.

        Raises:
            SecurityError: fichier dépassant la taille maximale autorisée.
            ValueError: PDF protégé par un mot de passe non vide.
        """
        import fitz

        check_file_size(path)
        self.path = path
        self._doc = fitz.open(path)
        if self._doc.is_encrypted and not self._doc.authenticate(""):
            self._doc.close()
            raise ValueError(
                f"Le PDF « {Path(path).name} » est protégé par mot de passe "
                "et ne peut pas être édité."
            )

    # ------------------------------------------------------------------ infos
    @property
    def page_count(self) -> int:
        """Nombre de pages du document."""
        return len(self._doc)

    def page_size(self, index: int) -> tuple[float, float]:
        """Largeur et hauteur d'une page, en points PDF."""
        rect = self._doc[index].rect
        return (rect.width, rect.height)

    def render_page(self, index: int, zoom: float = 1.0,
                    watermark: "Watermark | None" = None) -> bytes:
        """Rend une page en PNG, pour l'aperçu à l'écran.

        Quand un filigrane actif est fourni, il est appliqué sur une copie
        jetable de la page avant le rendu : l'aperçu emprunte exactement le
        même code que la sauvegarde, donc ce qui est affiché est ce qui sera
        écrit — sans approximation à recalibrer à chaque évolution du rendu.

        Args:
            index: index de page (0-based).
            zoom: facteur d'échelle (1.0 = 72 dpi, 2.0 = 144 dpi).
            watermark: filigrane à prévisualiser, ou None.

        Returns:
            Les octets d'une image PNG.
        """
        import fitz

        matrix = fitz.Matrix(zoom, zoom)
        if watermark and watermark.enabled:
            preview = fitz.open()
            try:
                preview.insert_pdf(self._doc, from_page=index, to_page=index)
                page = preview[0]
                self._apply_watermark(page, watermark)
                return page.get_pixmap(matrix=matrix).tobytes("png")
            finally:
                preview.close()
        return self._doc[index].get_pixmap(matrix=matrix).tobytes("png")

    def close(self) -> None:
        """Ferme le document et libère le fichier."""
        self._doc.close()

    # ------------------------------------------------------------------ rendu
    def save(
        self,
        output_path: str,
        annotations: list[Annotation] | None = None,
        watermark: Watermark | None = None,
    ) -> str:
        """Applique les annotations puis écrit le PDF résultant.

        Args:
            output_path: chemin souhaité (un suffixe _1, _2... est ajouté si
                le fichier existe déjà, pour ne jamais écraser).
            annotations: éléments à dessiner, dans l'ordre d'ajout.
            watermark: filigrane appliqué à toutes les pages si `enabled`.

        Returns:
            Chemin réel du fichier généré.
        """
        import fitz

        from utils.helpers import unique_path

        # Le rendu part d'une copie fraîche du fichier source, jamais du document
        # d'aperçu : deux sauvegardes successives produisent ainsi le même
        # résultat, au lieu d'empiler deux fois les annotations.
        doc = fitz.open(self.path)
        try:
            valid = [ann for ann in (annotations or []) if 0 <= ann.page < len(doc)]

            # Les caviardages sont appliqués d'abord, et par page : ils
            # suppriment réellement le contenu de la zone. Les traiter en
            # dernier effacerait aussi les annotations dessinées par-dessus.
            self._apply_redactions(doc, [a for a in valid if a.kind == "redact"])

            for ann in valid:
                if ann.kind != "redact":
                    self._apply_annotation(doc[ann.page], ann)

            if watermark and watermark.enabled:
                for page in doc:
                    self._apply_watermark(page, watermark)

            out = unique_path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(out))
        finally:
            doc.close()
        return str(out)

    @staticmethod
    def _apply_redactions(doc, redactions: list[Annotation]) -> None:
        """Supprime définitivement le contenu des zones caviardées.

        À la différence d'un rectangle noir, qui se contente de recouvrir, le
        caviardage retire le texte et les images de la zone : après traitement,
        un copier-coller ou une extraction ne restituent plus rien. C'est la
        seule façon honnête de masquer une donnée sensible.

        `apply_redactions()` s'applique à une page entière : les zones sont
        donc regroupées par page avant d'être exécutées en une passe.
        """
        import fitz

        by_page: dict[int, list[Annotation]] = {}
        for ann in redactions:
            by_page.setdefault(ann.page, []).append(ann)

        for index, anns in by_page.items():
            page = doc[index]
            for ann in anns:
                x0, y0, x1, y1 = ann.rect
                page.add_redact_annot(fitz.Rect(x0, y0, x1, y1),
                                      fill=ann.style.fill or ann.style.color)
            page.apply_redactions()

    def _apply_annotation(self, page, ann: Annotation) -> None:
        """Dessine une annotation sur une page, en routant selon son type."""
        handler = {
            "text": self._draw_text,
            "signature": self._draw_signature,
            "line": self._draw_line,
            "arrow": self._draw_arrow,
            "rect": self._draw_rect,
            "ellipse": self._draw_ellipse,
            "highlight": self._draw_highlight,
        }.get(ann.kind)
        if handler is None:
            raise ValueError(f"Type d'annotation inconnu : {ann.kind}")
        handler(page, ann)

    # ------------------------------------------------------------------ texte
    @staticmethod
    def _draw_text(page, ann: Annotation) -> None:
        """Écrit du texte, et trace le soulignement si le style le demande."""
        import fitz

        st = ann.style
        font = st.font
        page.insert_text(
            fitz.Point(ann.x0, ann.y0),
            ann.text,
            fontname=font,
            fontsize=st.size,
            color=st.color,
            fill_opacity=st.opacity,
        )
        if st.underline and ann.text:
            width = fitz.get_text_length(ann.text, fontname=font, fontsize=st.size)
            # Ligne posée juste sous la ligne de base, épaisseur proportionnelle
            # à la taille du texte pour rester lisible à toutes les échelles.
            y = ann.y0 + st.size * 0.12
            shape = page.new_shape()
            shape.draw_line(fitz.Point(ann.x0, y), fitz.Point(ann.x0 + width, y))
            shape.finish(color=st.color, width=max(0.5, st.size * 0.06),
                         stroke_opacity=st.opacity)
            shape.commit()

    # -------------------------------------------------------------- signature
    @staticmethod
    def _draw_signature(page, ann: Annotation) -> None:
        """Insère l'image de signature dans le rectangle tracé par l'utilisateur."""
        import fitz

        x0, y0, x1, y1 = ann.rect
        page.insert_image(fitz.Rect(x0, y0, x1, y1), filename=ann.image_path,
                          keep_proportion=True, overlay=True)

    # ------------------------------------------------------------------ formes
    @staticmethod
    def _draw_line(page, ann: Annotation) -> None:
        """Trace un segment entre les deux points."""
        import fitz

        st = ann.style
        shape = page.new_shape()
        shape.draw_line(fitz.Point(ann.x0, ann.y0), fitz.Point(ann.x1, ann.y1))
        shape.finish(color=st.color, width=st.line_width, stroke_opacity=st.opacity)
        shape.commit()

    @staticmethod
    def _draw_arrow(page, ann: Annotation) -> None:
        """Trace une flèche : segment + pointe triangulaire pleine à l'arrivée."""
        import fitz

        st = ann.style
        shape = page.new_shape()
        start = fitz.Point(ann.x0, ann.y0)
        end = fitz.Point(ann.x1, ann.y1)
        shape.draw_line(start, end)
        shape.finish(color=st.color, width=st.line_width, stroke_opacity=st.opacity)

        angle = math.atan2(ann.y1 - ann.y0, ann.x1 - ann.x0)
        head = max(6.0, st.line_width * 4.0)
        spread = math.radians(28)
        left = fitz.Point(ann.x1 - head * math.cos(angle - spread),
                          ann.y1 - head * math.sin(angle - spread))
        right = fitz.Point(ann.x1 - head * math.cos(angle + spread),
                           ann.y1 - head * math.sin(angle + spread))
        shape.draw_polyline([end, left, right, end])
        shape.finish(color=st.color, fill=st.color, width=st.line_width,
                     stroke_opacity=st.opacity, fill_opacity=st.opacity)
        shape.commit()

    @staticmethod
    def _draw_rect(page, ann: Annotation) -> None:
        """Trace un rectangle, rempli si un fond est défini dans le style."""
        import fitz

        st = ann.style
        x0, y0, x1, y1 = ann.rect
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(x0, y0, x1, y1))
        shape.finish(color=st.color, fill=st.fill, width=st.line_width,
                     stroke_opacity=st.opacity, fill_opacity=st.opacity)
        shape.commit()

    @staticmethod
    def _draw_ellipse(page, ann: Annotation) -> None:
        """Trace une ellipse inscrite dans le rectangle tracé."""
        import fitz

        st = ann.style
        x0, y0, x1, y1 = ann.rect
        shape = page.new_shape()
        shape.draw_oval(fitz.Rect(x0, y0, x1, y1))
        shape.finish(color=st.color, fill=st.fill, width=st.line_width,
                     stroke_opacity=st.opacity, fill_opacity=st.opacity)
        shape.commit()

    @staticmethod
    def _draw_highlight(page, ann: Annotation) -> None:
        """Surligne une zone : rectangle plein semi-transparent, sans contour.

        L'opacité est plafonnée pour que le texte sous-jacent reste lisible,
        même si l'utilisateur a monté l'opacité pour un autre outil.
        """
        import fitz

        st = ann.style
        x0, y0, x1, y1 = ann.rect
        color = st.fill or st.color
        shape = page.new_shape()
        shape.draw_rect(fitz.Rect(x0, y0, x1, y1))
        shape.finish(color=None, fill=color, fill_opacity=min(st.opacity, 0.45))
        shape.commit()

    # --------------------------------------------------------------- filigrane
    @staticmethod
    def _apply_watermark(page, wm: Watermark) -> None:
        """Écrit le filigrane en diagonale, centré sur la page, en lettres évidées.

        Le texte est centré sur sa propre largeur mesurée, puis pivoté autour du
        centre de la page via `morph` — `insert_text(rotate=...)` ne gère que les
        multiples de 90°, insuffisant pour une diagonale.

        Le rendu combine contour et remplissage (`render_mode=2`) : le contour
        porte la lisibilité du mot, tandis que l'intérieur, presque transparent,
        laisse passer le texte du document sans le voiler.

        Le filigrane est posé par-dessus le contenu, et non dessous : sur un PDF
        issu d'un scan (une image pleine page), le placer dessous le rendrait
        totalement invisible — une case cochée sans effet visible serait un
        échec silencieux bien plus gênant qu'un léger recouvrement.
        """
        import fitz

        rect = page.rect
        cx, cy = rect.width / 2, rect.height / 2
        width = fitz.get_text_length(wm.text, fontname="hebo", fontsize=wm.size)
        origin = fitz.Point(cx - width / 2, cy + wm.size * 0.35)
        pivot = fitz.Point(cx, cy)

        page.insert_text(
            origin,
            wm.text,
            fontname="hebo",
            fontsize=wm.size,
            color=wm.color,
            fill=wm.color,
            render_mode=2,
            border_width=WATERMARK_BORDER_WIDTH,
            stroke_opacity=wm.opacity,
            fill_opacity=wm.opacity * WATERMARK_FILL_RATIO,
            morph=(pivot, fitz.Matrix(wm.rotation)),
        )
