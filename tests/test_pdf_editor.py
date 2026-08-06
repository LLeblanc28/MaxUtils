"""Tests du moteur d'édition PDF (core/pdf_editor.py) et de la génération de
signature (core/signature.py).

Les rendus sont vérifiés sur le PDF réellement produit — texte extrait, nombre
de pages, présence du filigrane — et non sur la seule absence d'exception.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pdf_editor import (
    COLORS,
    FONT_FAMILIES,
    Annotation,
    PdfEditor,
    Style,
    Watermark,
    resolve_font,
)
from core.signature import render_signature
from utils.security import SecurityError


def _build_pdf(path: Path, pages: int = 1, text: str = "Contenu") -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    for i in range(pages):
        c.drawString(72, 780, f"{text} {i + 1}")
        c.showPage()
    c.save()


def _make_signature_png(path: Path) -> None:
    from PIL import Image

    Image.new("RGBA", (120, 60), (0, 0, 200, 255)).save(path)


class TestResolveFont(unittest.TestCase):
    def test_all_families_and_styles(self):
        self.assertEqual(resolve_font("helv"), "helv")
        self.assertEqual(resolve_font("helv", bold=True), "hebo")
        self.assertEqual(resolve_font("helv", italic=True), "heit")
        self.assertEqual(resolve_font("helv", bold=True, italic=True), "hebi")
        self.assertEqual(resolve_font("tiro"), "tiro")
        self.assertEqual(resolve_font("tiro", bold=True, italic=True), "tibi")
        self.assertEqual(resolve_font("cour", bold=True), "cobo")
        self.assertEqual(resolve_font("cour", italic=True), "coit")

    def test_unknown_family_falls_back_to_helvetica(self):
        self.assertEqual(resolve_font("comic-sans"), "helv")

    def test_font_families_map_to_known_codes(self):
        for code in FONT_FAMILIES.values():
            self.assertEqual(resolve_font(code), resolve_font(code, False, False))


class TestStyleAndAnnotation(unittest.TestCase):
    def test_style_font_property_reflects_flags(self):
        self.assertEqual(Style(family="tiro", bold=True).font, "tibo")
        self.assertEqual(Style().font, "helv")

    def test_rect_normalises_reversed_coordinates(self):
        # Zone tracée de bas-droite vers haut-gauche : le rectangle doit rester
        # valide (x0 <= x1, y0 <= y1) quel que soit le sens du glisser.
        ann = Annotation("rect", 0, 300, 400, 100, 200)
        self.assertEqual(ann.rect, (100, 200, 300, 400))

    def test_rect_already_ordered(self):
        ann = Annotation("rect", 0, 10, 20, 30, 40)
        self.assertEqual(ann.rect, (10, 20, 30, 40))


class TestPdfEditorBasics(unittest.TestCase):
    def test_page_count_size_and_render(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=3)
            editor = PdfEditor(str(src))
            try:
                self.assertEqual(editor.page_count, 3)
                width, height = editor.page_size(0)
                self.assertGreater(width, 500)
                self.assertGreater(height, 800)

                png = editor.render_page(0, zoom=1.0)
                self.assertTrue(png.startswith(b"\x89PNG"))
                bigger = editor.render_page(0, zoom=2.0)
                self.assertGreater(len(bigger), len(png))
            finally:
                editor.close()

    def test_render_page_previews_the_watermark_without_altering_the_document(self):
        # L'aperçu doit montrer le filigrane, mais la page d'origine ne doit
        # pas en garder trace : sinon un simple aperçu le graverait dans le
        # document, et le décocher ne l'enlèverait plus.
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src)
            editor = PdfEditor(str(src))
            try:
                plain = editor.render_page(0)
                marked = editor.render_page(0, watermark=Watermark(enabled=True))
                self.assertNotEqual(plain, marked)

                # Filigrane désactivé, puis absent : on retrouve l'image d'origine.
                self.assertEqual(editor.render_page(0, watermark=Watermark(enabled=False)), plain)
                self.assertEqual(editor.render_page(0), plain)
            finally:
                editor.close()

    def test_oversized_pdf_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src)
            with patch("core.pdf_editor.check_file_size",
                       side_effect=SecurityError("trop volumineux")):
                with self.assertRaises(SecurityError):
                    PdfEditor(str(src))

    def test_password_protected_pdf_rejected(self):
        from pypdf import PdfReader, PdfWriter

        with tempfile.TemporaryDirectory() as tmp_dir:
            plain = Path(tmp_dir) / "plain.pdf"
            _build_pdf(plain)
            encrypted = Path(tmp_dir) / "locked.pdf"
            writer = PdfWriter()
            for page in PdfReader(str(plain)).pages:
                writer.add_page(page)
            writer.encrypt("s3cret")
            with open(encrypted, "wb") as f:
                writer.write(f)

            with self.assertRaises(ValueError) as ctx:
                PdfEditor(str(encrypted))
            self.assertIn("mot de passe", str(ctx.exception))


class TestPdfEditorSave(unittest.TestCase):
    def _editor(self, tmp_dir, pages=1):
        src = Path(tmp_dir) / "doc.pdf"
        _build_pdf(src, pages=pages)
        return PdfEditor(str(src))

    def test_text_with_all_style_options(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            editor = self._editor(tmp_dir)
            try:
                anns = [
                    Annotation("text", 0, 60, 100, text="Souligné gras",
                               style=Style(size=18, bold=True, underline=True,
                                           color=COLORS["Rouge"])),
                    Annotation("text", 0, 60, 140, text="Times italique",
                               style=Style(family="tiro", italic=True)),
                    # Souligné demandé mais texte vide : la ligne ne doit pas
                    # être tracée, et surtout rien ne doit planter.
                    Annotation("text", 0, 60, 180, text="",
                               style=Style(underline=True)),
                ]
                out = editor.save(str(Path(tmp_dir) / "out.pdf"), anns)
            finally:
                editor.close()

            import fitz
            doc = fitz.open(out)
            text = doc[0].get_text()
            doc.close()
            self.assertIn("Souligné gras", text)
            self.assertIn("Times italique", text)

    def test_every_shape_kind_is_drawn(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sig = Path(tmp_dir) / "sig.png"
            _make_signature_png(sig)
            editor = self._editor(tmp_dir)
            try:
                anns = [
                    Annotation("line", 0, 50, 200, 300, 200, style=Style(line_width=2)),
                    Annotation("arrow", 0, 50, 240, 300, 300,
                               style=Style(line_width=3, color=COLORS["Bleu"])),
                    Annotation("rect", 0, 50, 330, 250, 420,
                               style=Style(fill=COLORS["Jaune"])),
                    Annotation("rect", 0, 260, 330, 400, 420, style=Style(fill=None)),
                    Annotation("ellipse", 0, 50, 440, 250, 520,
                               style=Style(fill=COLORS["Vert"])),
                    Annotation("ellipse", 0, 260, 440, 400, 520, style=Style(fill=None)),
                    Annotation("highlight", 0, 50, 540, 400, 570,
                               style=Style(fill=COLORS["Jaune"])),
                    # Surlignage sans remplissage : retombe sur la couleur de trait.
                    Annotation("highlight", 0, 50, 580, 400, 610, style=Style(fill=None)),
                    Annotation("signature", 0, 350, 640, 500, 700, image_path=str(sig)),
                ]
                out = editor.save(str(Path(tmp_dir) / "out.pdf"), anns)
            finally:
                editor.close()
            self.assertTrue(Path(out).exists())
            self.assertGreater(Path(out).stat().st_size, 1000)

    def test_arrow_pointing_in_each_direction(self):
        # La pointe est calculée par trigonométrie : on vérifie que les quatre
        # sens cardinaux passent, y compris la flèche de longueur nulle.
        with tempfile.TemporaryDirectory() as tmp_dir:
            editor = self._editor(tmp_dir)
            try:
                anns = [
                    Annotation("arrow", 0, 100, 100, 300, 100),
                    Annotation("arrow", 0, 300, 200, 100, 200),
                    Annotation("arrow", 0, 100, 300, 100, 500),
                    Annotation("arrow", 0, 200, 600, 200, 400),
                    Annotation("arrow", 0, 400, 400, 400, 400),
                ]
                out = editor.save(str(Path(tmp_dir) / "out.pdf"), anns)
            finally:
                editor.close()
            self.assertTrue(Path(out).exists())

    def test_unknown_annotation_kind_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            editor = self._editor(tmp_dir)
            try:
                with self.assertRaises(ValueError):
                    editor.save(str(Path(tmp_dir) / "out.pdf"),
                                [Annotation("licorne", 0, 10, 10, 20, 20)])
            finally:
                editor.close()

    def test_out_of_range_page_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            editor = self._editor(tmp_dir, pages=1)
            try:
                out = editor.save(str(Path(tmp_dir) / "out.pdf"), [
                    Annotation("text", 5, 10, 10, text="page inexistante"),
                    Annotation("text", -1, 10, 10, text="index négatif"),
                ])
            finally:
                editor.close()

            import fitz
            doc = fitz.open(out)
            text = doc[0].get_text()
            doc.close()
            self.assertNotIn("page inexistante", text)
            self.assertNotIn("index négatif", text)

    def test_save_without_annotations_or_watermark(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            editor = self._editor(tmp_dir)
            try:
                out = editor.save(str(Path(tmp_dir) / "copie.pdf"))
            finally:
                editor.close()
            self.assertTrue(Path(out).exists())

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            editor = self._editor(tmp_dir)
            try:
                target = str(Path(tmp_dir) / "out.pdf")
                first = editor.save(target)
                second = editor.save(target)
            finally:
                editor.close()
            self.assertNotEqual(first, second)
            self.assertTrue(Path(first).exists())
            self.assertTrue(Path(second).exists())

    def test_repeated_save_is_idempotent(self):
        # Régression : le rendu doit repartir du fichier source à chaque appel.
        # Sinon les annotations s'empilent et la deuxième sauvegarde contient
        # le texte en double.
        with tempfile.TemporaryDirectory() as tmp_dir:
            editor = self._editor(tmp_dir)
            anns = [Annotation("text", 0, 60, 100, text="UNIQUE")]
            try:
                editor.save(str(Path(tmp_dir) / "a.pdf"), anns)
                second = editor.save(str(Path(tmp_dir) / "b.pdf"), anns)
            finally:
                editor.close()

            import fitz
            doc = fitz.open(second)
            text = doc[0].get_text()
            doc.close()
            self.assertEqual(text.count("UNIQUE"), 1)


class TestRedaction(unittest.TestCase):
    """Le caviardage doit supprimer le contenu, pas seulement le recouvrir.

    Un rectangle noir laisse le texte intact dans le fichier : un copier-coller
    le restitue intégralement. Ces tests vérifient que le caviardage, lui,
    l'efface réellement — y compris des octets bruts du fichier.
    """

    def _sensitive_pdf(self, path: Path) -> None:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        c = canvas.Canvas(str(path), pagesize=A4)
        c.setFont("Helvetica", 12)
        c.drawString(72, 700, "IBAN CONFIDENTIEL FR7630004")
        c.drawString(72, 640, "Ligne publique a conserver")
        c.showPage()
        c.save()

    def test_redacted_text_is_gone_from_the_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            self._sensitive_pdf(src)
            editor = PdfEditor(str(src))
            try:
                out = editor.save(str(Path(tmp_dir) / "caviarde.pdf"), [
                    Annotation("redact", 0, 60, 130, 420, 160,
                               style=Style(fill=(0.0, 0.0, 0.0))),
                ])
            finally:
                editor.close()

            import fitz
            doc = fitz.open(out)
            text = doc[0].get_text()
            doc.close()

            self.assertNotIn("FR7630004", text)
            self.assertIn("conserver", text)      # le reste du document survit
            # Preuve la plus forte : la donnée n'est plus dans le fichier du tout.
            self.assertNotIn(b"FR7630004", Path(out).read_bytes())

    def test_a_plain_rectangle_does_not_remove_anything(self):
        # Test de contraste : il documente précisément pourquoi l'outil
        # « Caviarder » existe à côté de l'outil « Rectangle ».
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            self._sensitive_pdf(src)
            editor = PdfEditor(str(src))
            try:
                out = editor.save(str(Path(tmp_dir) / "masque.pdf"), [
                    Annotation("rect", 0, 60, 130, 420, 160,
                               style=Style(fill=(0.0, 0.0, 0.0))),
                ])
            finally:
                editor.close()

            import fitz
            doc = fitz.open(out)
            text = doc[0].get_text()
            doc.close()
            self.assertIn("FR7630004", text)

    def test_several_zones_on_several_pages(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=3, text="SECRET")
            editor = PdfEditor(str(src))
            try:
                out = editor.save(str(Path(tmp_dir) / "out.pdf"), [
                    Annotation("redact", 0, 50, 40, 500, 80),
                    Annotation("redact", 0, 50, 90, 500, 130),
                    Annotation("redact", 2, 50, 40, 500, 80),
                ])
            finally:
                editor.close()

            import fitz
            doc = fitz.open(out)
            try:
                self.assertNotIn("SECRET", doc[0].get_text())
                self.assertIn("SECRET", doc[1].get_text())   # page non caviardée
                self.assertNotIn("SECRET", doc[2].get_text())
            finally:
                doc.close()

    def test_annotations_drawn_over_a_redaction_survive(self):
        # Les caviardages sont appliqués en premier : une annotation posée
        # au même endroit ne doit pas être effacée par eux.
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            self._sensitive_pdf(src)
            editor = PdfEditor(str(src))
            try:
                out = editor.save(str(Path(tmp_dir) / "out.pdf"), [
                    Annotation("redact", 0, 60, 130, 420, 160),
                    Annotation("text", 0, 70, 150, text="MASQUE",
                               style=Style(size=14, color=(1.0, 1.0, 1.0))),
                ])
            finally:
                editor.close()

            import fitz
            doc = fitz.open(out)
            text = doc[0].get_text()
            doc.close()
            self.assertIn("MASQUE", text)
            self.assertNotIn("FR7630004", text)

    def test_redaction_without_explicit_fill_uses_the_stroke_colour(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            self._sensitive_pdf(src)
            editor = PdfEditor(str(src))
            try:
                out = editor.save(str(Path(tmp_dir) / "out.pdf"), [
                    Annotation("redact", 0, 60, 130, 420, 160,
                               style=Style(fill=None, color=(0.2, 0.2, 0.2))),
                ])
            finally:
                editor.close()
            self.assertTrue(Path(out).exists())


class TestWatermark(unittest.TestCase):
    def test_watermark_applied_to_every_page(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=3)
            editor = PdfEditor(str(src))
            try:
                out = editor.save(str(Path(tmp_dir) / "out.pdf"),
                                  watermark=Watermark(enabled=True))
            finally:
                editor.close()

            import fitz
            doc = fitz.open(out)
            try:
                self.assertEqual(len(doc), 3)
                for page in doc:
                    self.assertIn("CONFIDENTIEL", page.get_text())
            finally:
                doc.close()

    def test_watermark_disabled_leaves_document_clean(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src)
            editor = PdfEditor(str(src))
            try:
                out = editor.save(str(Path(tmp_dir) / "out.pdf"),
                                  watermark=Watermark(enabled=False))
            finally:
                editor.close()

            import fitz
            doc = fitz.open(out)
            text = doc[0].get_text()
            doc.close()
            self.assertNotIn("CONFIDENTIEL", text)

    def test_watermark_letters_are_hollow_so_text_stays_readable(self):
        # Le contour doit être nettement plus opaque que l'intérieur : c'est ce
        # qui rend le mot lisible sans poser de voile sur le texte du document.
        # Un rendu en aplat (contour et intérieur de même opacité) casserait la
        # lisibilité et doit faire échouer ce test.
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src)
            editor = PdfEditor(str(src))
            captured = {}

            import fitz
            real_insert = fitz.Page.insert_text

            def spy(page, point, text, **kwargs):
                if text == "CONFIDENTIEL":
                    captured.update(kwargs)
                return real_insert(page, point, text, **kwargs)

            try:
                with patch.object(fitz.Page, "insert_text", spy):
                    editor.save(str(Path(tmp_dir) / "out.pdf"),
                                watermark=Watermark(enabled=True, opacity=0.45))
            finally:
                editor.close()

            self.assertEqual(captured["render_mode"], 2)  # contour + remplissage
            self.assertGreater(captured["border_width"], 0)
            self.assertLess(captured["fill_opacity"], captured["stroke_opacity"] / 2)

    def test_watermark_barely_darkens_the_page(self):
        # Vérification perceptuelle : la page filigranée doit rester presque
        # aussi claire que l'originale, sinon le filigrane « gêne la lecture ».
        from PIL import Image, ImageStat

        def mean_brightness(pdf_path: str) -> float:
            import fitz

            doc = fitz.open(pdf_path)
            pix = doc[0].get_pixmap()
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("L")
            doc.close()
            return ImageStat.Stat(img).mean[0]

        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src)
            editor = PdfEditor(str(src))
            try:
                marked = editor.save(str(Path(tmp_dir) / "out.pdf"),
                                     watermark=Watermark(enabled=True))
            finally:
                editor.close()

            clean = mean_brightness(str(src))
            self.assertLess(clean - mean_brightness(marked), 4.0)

    def test_custom_watermark_text_and_appearance(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src)
            editor = PdfEditor(str(src))
            try:
                out = editor.save(
                    str(Path(tmp_dir) / "out.pdf"),
                    watermark=Watermark(enabled=True, text="BROUILLON", size=90,
                                        color=COLORS["Bleu"], opacity=0.4, rotation=30),
                )
            finally:
                editor.close()

            import fitz
            doc = fitz.open(out)
            text = doc[0].get_text()
            doc.close()
            self.assertIn("BROUILLON", text)


class TestRenderSignature(unittest.TestCase):
    def test_strokes_produce_cropped_transparent_png(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp_dir:
            out = Path(tmp_dir) / "sig.png"
            path = render_signature(
                [[(10, 10), (60, 40), (110, 15)], [(20, 50), (100, 55)]],
                str(out), color=(0, 0, 1), width=4, padding=10,
            )
            self.assertEqual(path, str(out))
            with Image.open(path) as img:
                self.assertEqual(img.mode, "RGBA")
                # Recadré sur le tracé (largeur ~100) plus 2x la marge.
                self.assertLess(img.width, 140)
                self.assertEqual(img.getpixel((0, 0))[3], 0)  # coin transparent

    def test_single_point_stroke_draws_a_dot(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out = Path(tmp_dir) / "dot.png"
            path = render_signature([[(30, 30)]], str(out), width=6)
            self.assertTrue(Path(path).exists())

    def test_empty_strokes_raises_value_error(self):
        with self.assertRaises(ValueError):
            render_signature([])

    def test_strokes_containing_only_empty_lists_raises(self):
        with self.assertRaises(ValueError):
            render_signature([[], []])

    def test_default_output_path_is_generated(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("core.signature.SIGNATURE_DIR", Path(tmp_dir) / "sigs"):
                path = render_signature([[(0, 0), (20, 20)]])
            self.assertTrue(Path(path).exists())
            self.assertTrue(Path(path).name.startswith("signature_"))


if __name__ == "__main__":
    unittest.main()
