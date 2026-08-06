"""Tests des opérations sur document PDF : découpe, compression, protection.

Les résultats sont vérifiés sur les fichiers réellement produits (nombre de
pages, contenu extrait, ouverture avec et sans mot de passe), pas seulement
sur l'absence d'exception.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pdf_tools import (
    COMPRESSION_LEVELS,
    NUMBER_POSITIONS,
    add_page_numbers,
    compress_pdf,
    extract_images,
    extract_text,
    organize_pages,
    page_count,
    protect_pdf,
    render_thumbnail,
    split_pdf,
    unlock_pdf,
)
from utils.security import SecurityError


def _build_pdf(path: Path, pages: int = 5) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    for i in range(pages):
        c.drawString(72, 780, f"PAGE NUMERO {i + 1}")
        c.showPage()
    c.save()


def _encrypt(src: Path, dest: Path, password: str = "s3cret") -> None:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for page in PdfReader(str(src)).pages:
        writer.add_page(page)
    writer.encrypt(password)
    with open(dest, "wb") as f:
        writer.write(f)


def _text_of(pdf_path: str, index: int = 0) -> str:
    import fitz

    doc = fitz.open(pdf_path)
    try:
        return doc[index].get_text()
    finally:
        doc.close()


class TestPageCount(unittest.TestCase):
    def test_counts_pages(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=7)
            self.assertEqual(page_count(str(src)), 7)

    def test_locked_document_without_password_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plain, locked = Path(tmp_dir) / "a.pdf", Path(tmp_dir) / "b.pdf"
            _build_pdf(plain, pages=2)
            _encrypt(plain, locked)
            with self.assertRaises(ValueError) as ctx:
                page_count(str(locked))
            self.assertIn("protégé", str(ctx.exception))

    def test_locked_document_with_wrong_password_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plain, locked = Path(tmp_dir) / "a.pdf", Path(tmp_dir) / "b.pdf"
            _build_pdf(plain, pages=2)
            _encrypt(plain, locked)
            with self.assertRaises(ValueError) as ctx:
                page_count(str(locked), password="mauvais")
            self.assertIn("incorrect", str(ctx.exception))

    def test_locked_document_with_correct_password_works(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plain, locked = Path(tmp_dir) / "a.pdf", Path(tmp_dir) / "b.pdf"
            _build_pdf(plain, pages=3)
            _encrypt(plain, locked)
            self.assertEqual(page_count(str(locked), password="s3cret"), 3)

    def test_oversized_document_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=1)
            with patch("core.pdf_tools.check_file_size",
                       side_effect=SecurityError("trop volumineux")):
                with self.assertRaises(SecurityError):
                    page_count(str(src))


class TestSplitPdf(unittest.TestCase):
    def test_extract_range_into_single_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=5)
            created = split_pdf(str(src), tmp_dir, page_ranges="2-3")

            self.assertEqual(len(created), 1)
            self.assertEqual(page_count(created[0]), 2)
            self.assertIn("PAGE NUMERO 2", _text_of(created[0], 0))
            self.assertIn("PAGE NUMERO 3", _text_of(created[0], 1))

    def test_extract_respects_requested_order(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=5)
            created = split_pdf(str(src), tmp_dir, page_ranges="4,1")
            self.assertIn("PAGE NUMERO 4", _text_of(created[0], 0))
            self.assertIn("PAGE NUMERO 1", _text_of(created[0], 1))

    def test_empty_range_extracts_everything(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=4)
            created = split_pdf(str(src), tmp_dir)
            self.assertEqual(page_count(created[0]), 4)

    def test_per_page_produces_one_file_per_page(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=3)
            created = split_pdf(str(src), tmp_dir, per_page=True)

            self.assertEqual(len(created), 3)
            for i, path in enumerate(created):
                self.assertEqual(page_count(path), 1)
                self.assertIn(f"PAGE NUMERO {i + 1}", _text_of(path))

    def test_per_page_honours_the_selected_range(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=5)
            created = split_pdf(str(src), tmp_dir, page_ranges="2,5", per_page=True)
            self.assertEqual(len(created), 2)
            self.assertIn("PAGE NUMERO 2", _text_of(created[0]))
            self.assertIn("PAGE NUMERO 5", _text_of(created[1]))

    def test_out_of_bounds_range_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=3)
            with self.assertRaises(ValueError):
                split_pdf(str(src), tmp_dir, page_ranges="1-9")

    def test_source_file_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=4)
            before = src.read_bytes()
            split_pdf(str(src), tmp_dir, page_ranges="2", per_page=True)
            self.assertEqual(src.read_bytes(), before)

    def test_existing_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=2)
            first = split_pdf(str(src), tmp_dir, page_ranges="1")[0]
            second = split_pdf(str(src), tmp_dir, page_ranges="1")[0]
            self.assertNotEqual(first, second)
            self.assertTrue(Path(first).exists())

    def test_split_of_protected_document_with_password(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plain, locked = Path(tmp_dir) / "a.pdf", Path(tmp_dir) / "b.pdf"
            _build_pdf(plain, pages=4)
            _encrypt(plain, locked)
            created = split_pdf(str(locked), tmp_dir, page_ranges="1-2",
                                password="s3cret")
            self.assertEqual(page_count(created[0]), 2)


class TestOrganizePages(unittest.TestCase):
    def test_reordering_pages(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=3)
            out = organize_pages(str(src), str(Path(tmp_dir) / "o.pdf"),
                                 [(2, 0), (0, 0), (1, 0)])
            self.assertIn("PAGE NUMERO 3", _text_of(out, 0))
            self.assertIn("PAGE NUMERO 1", _text_of(out, 1))
            self.assertIn("PAGE NUMERO 2", _text_of(out, 2))

    def test_deleting_pages_by_omitting_them(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=5)
            out = organize_pages(str(src), str(Path(tmp_dir) / "o.pdf"),
                                 [(0, 0), (4, 0)])
            self.assertEqual(page_count(out), 2)
            self.assertIn("PAGE NUMERO 5", _text_of(out, 1))

    def test_rotating_a_single_page(self):
        import fitz

        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=2)
            out = organize_pages(str(src), str(Path(tmp_dir) / "o.pdf"),
                                 [(0, 90), (1, 0)])
            doc = fitz.open(out)
            try:
                self.assertEqual(doc[0].rotation, 90)
                self.assertEqual(doc[1].rotation, 0)
            finally:
                doc.close()

    def test_rotation_adds_to_an_already_rotated_page(self):
        # Une page déjà de travers doit pouvoir être redressée par un quart de
        # tour supplémentaire, pas repartir de zéro.
        import fitz

        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=1)
            tilted = Path(tmp_dir) / "penche.pdf"
            doc = fitz.open(str(src))
            doc[0].set_rotation(270)
            doc.save(str(tilted))
            doc.close()

            out = organize_pages(str(tilted), str(Path(tmp_dir) / "o.pdf"), [(0, 90)])
            doc = fitz.open(out)
            try:
                self.assertEqual(doc[0].rotation, 0)   # 270 + 90 = 360 → 0
            finally:
                doc.close()

    def test_duplicating_a_page(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=2)
            out = organize_pages(str(src), str(Path(tmp_dir) / "o.pdf"),
                                 [(0, 0), (0, 0), (1, 0)])
            self.assertEqual(page_count(out), 3)

    def test_empty_selection_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=2)
            with self.assertRaises(ValueError) as ctx:
                organize_pages(str(src), str(Path(tmp_dir) / "o.pdf"), [])
            self.assertIn("au moins une page", str(ctx.exception))

    def test_out_of_range_index_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=2)
            with self.assertRaises(ValueError):
                organize_pages(str(src), str(Path(tmp_dir) / "o.pdf"), [(0, 0), (9, 0)])

    def test_source_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=3)
            before = src.read_bytes()
            organize_pages(str(src), str(Path(tmp_dir) / "o.pdf"), [(2, 180)])
            self.assertEqual(src.read_bytes(), before)

    def test_works_on_a_protected_document(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plain, locked = Path(tmp_dir) / "a.pdf", Path(tmp_dir) / "b.pdf"
            _build_pdf(plain, pages=3)
            _encrypt(plain, locked)
            out = organize_pages(str(locked), str(Path(tmp_dir) / "o.pdf"),
                                 [(1, 0)], password="s3cret")
            self.assertEqual(page_count(out), 1)


class TestRenderThumbnail(unittest.TestCase):
    def test_produces_a_png_at_the_requested_width(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=2)
            png = render_thumbnail(str(src), 1, width=120)
            self.assertTrue(png.startswith(b"\x89PNG"))

            import io
            with Image.open(io.BytesIO(png)) as img:
                self.assertEqual(img.width, 120)
                self.assertGreater(img.height, img.width)   # A4 est plus haut que large

    def test_thumbnail_of_a_protected_document(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plain, locked = Path(tmp_dir) / "a.pdf", Path(tmp_dir) / "b.pdf"
            _build_pdf(plain, pages=1)
            _encrypt(plain, locked)
            png = render_thumbnail(str(locked), 0, password="s3cret")
            self.assertTrue(png.startswith(b"\x89PNG"))


class TestCompressPdf(unittest.TestCase):
    def test_every_level_produces_a_readable_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=6)
            for level in COMPRESSION_LEVELS:
                out, before, after = compress_pdf(
                    str(src), str(Path(tmp_dir) / f"{level}.pdf"), level=level)
                self.assertTrue(Path(out).exists())
                self.assertEqual(page_count(out), 6)
                self.assertEqual(before, src.stat().st_size)
                self.assertEqual(after, Path(out).stat().st_size)

    def test_content_survives_compression(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=2)
            out, _, _ = compress_pdf(str(src), str(Path(tmp_dir) / "c.pdf"))
            self.assertIn("PAGE NUMERO 1", _text_of(out))

    def test_unknown_level_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=1)
            with self.assertRaises(ValueError):
                compress_pdf(str(src), str(Path(tmp_dir) / "c.pdf"), level="Ultra")

    def test_compression_of_protected_document(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plain, locked = Path(tmp_dir) / "a.pdf", Path(tmp_dir) / "b.pdf"
            _build_pdf(plain, pages=2)
            _encrypt(plain, locked)
            out, _, _ = compress_pdf(str(locked), str(Path(tmp_dir) / "c.pdf"),
                                     password="s3cret")
            self.assertEqual(page_count(out), 2)


class TestExtractText(unittest.TestCase):
    def test_extraction_to_txt(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=3)
            out, length = extract_text(str(src), str(Path(tmp_dir) / "texte.txt"))

            content = Path(out).read_text(encoding="utf-8")
            self.assertIn("PAGE NUMERO 1", content)
            self.assertIn("PAGE NUMERO 3", content)
            self.assertIn("--- Page 2 ---", content)   # séparateur entre pages
            self.assertGreater(length, 0)

    def test_extraction_to_docx(self):
        from docx import Document

        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=2)
            out, _ = extract_text(str(src), str(Path(tmp_dir) / "texte.docx"))

            document = Document(out)
            texts = "\n".join(p.text for p in document.paragraphs)
            self.assertIn("PAGE NUMERO 1", texts)
            self.assertIn("PAGE NUMERO 2", texts)

    def test_missing_python_docx_gives_an_actionable_message(self):
        # Une ImportError brute ne dit rien à l'utilisateur : il doit apprendre
        # quel paquet installer, comme pour pillow-heif ou py7zr.
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=1)
            with patch.dict(sys.modules, {"docx": None}):
                with self.assertRaises(RuntimeError) as ctx:
                    extract_text(str(src), str(Path(tmp_dir) / "texte.docx"))
            self.assertIn("python-docx", str(ctx.exception))

    def test_scanned_pdf_reports_zero_characters(self):
        # Un PDF sans couche de texte doit être signalé comme tel : livrer un
        # fichier vide sans explication laisserait croire à un bug.
        import fitz

        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "scan.pdf"
            doc = fitz.open()
            doc.new_page()
            doc.save(str(src))
            doc.close()

            _out, length = extract_text(str(src), str(Path(tmp_dir) / "vide.txt"))
            self.assertEqual(length, 0)

    def test_unsupported_output_format_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=1)
            with self.assertRaises(ValueError):
                extract_text(str(src), str(Path(tmp_dir) / "texte.odt"))

    def test_extraction_from_a_protected_document(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plain, locked = Path(tmp_dir) / "a.pdf", Path(tmp_dir) / "b.pdf"
            _build_pdf(plain, pages=1)
            _encrypt(plain, locked)
            out, length = extract_text(str(locked), str(Path(tmp_dir) / "t.txt"),
                                       password="s3cret")
            self.assertGreater(length, 0)
            self.assertIn("PAGE NUMERO 1", Path(out).read_text(encoding="utf-8"))


class TestExtractImages(unittest.TestCase):
    def _pdf_with_image(self, path: Path, count: int = 1) -> None:
        import fitz
        from PIL import Image

        doc = fitz.open()
        for i in range(count):
            page = doc.new_page()
            buffer = Path(str(path) + f".src{i}.png")
            Image.new("RGB", (120, 90), (30 * (i + 1), 60, 200)).save(buffer)
            page.insert_image(fitz.Rect(50, 50, 250, 200), filename=str(buffer))
        doc.save(str(path))
        doc.close()

    def test_extracts_embedded_images(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            self._pdf_with_image(src, count=2)
            out_dir = Path(tmp_dir) / "images"

            created = extract_images(str(src), str(out_dir))
            self.assertEqual(len(created), 2)
            for path in created:
                self.assertTrue(Path(path).exists())
                self.assertGreater(Path(path).stat().st_size, 0)

    def test_a_pdf_without_images_yields_nothing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=2)
            self.assertEqual(extract_images(str(src), tmp_dir), [])

    def test_tiny_images_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            self._pdf_with_image(src, count=1)
            # Seuil démesuré : plus rien ne doit passer.
            self.assertEqual(
                extract_images(str(src), tmp_dir, min_size=10_000_000), [])

    def test_an_image_repeated_on_several_pages_is_extracted_once(self):
        import fitz
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp_dir:
            logo = Path(tmp_dir) / "logo.png"
            Image.new("RGB", (100, 100), "red").save(logo)
            src = Path(tmp_dir) / "doc.pdf"
            doc = fitz.open()
            for _ in range(3):
                doc.new_page().insert_image(fitz.Rect(10, 10, 110, 110),
                                            filename=str(logo))
            doc.save(str(src))
            doc.close()

            created = extract_images(str(src), str(Path(tmp_dir) / "out"))
            self.assertEqual(len(created), 1)


class TestAddPageNumbers(unittest.TestCase):
    def test_numbers_every_page(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=3)
            out = add_page_numbers(str(src), str(Path(tmp_dir) / "n.pdf"))
            for i in range(3):
                self.assertIn(str(i + 1), _text_of(out, i))

    def test_format_with_total(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=4)
            out = add_page_numbers(str(src), str(Path(tmp_dir) / "n.pdf"),
                                   number_format="{n} / {total}")
            self.assertIn("1 / 4", _text_of(out, 0))
            self.assertIn("4 / 4", _text_of(out, 3))

    def test_start_at_a_chosen_number(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=2)
            out = add_page_numbers(str(src), str(Path(tmp_dir) / "n.pdf"), start_at=10)
            self.assertIn("10", _text_of(out, 0))
            self.assertIn("11", _text_of(out, 1))

    def test_cover_page_can_be_skipped(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=3)
            out = add_page_numbers(str(src), str(Path(tmp_dir) / "n.pdf"),
                                   skip_first=True, number_format="Page {n}")
            self.assertNotIn("Page ", _text_of(out, 0))
            # La numérotation reprend à 1 sur la page suivante.
            self.assertIn("Page 1", _text_of(out, 1))
            self.assertIn("Page 2", _text_of(out, 2))

    def test_every_position_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=1)
            for position in NUMBER_POSITIONS:
                out = add_page_numbers(str(src), str(Path(tmp_dir) / "n.pdf"),
                                       position=position)
                self.assertIn("1", _text_of(out))

    def test_header_and_footer(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=2)
            out = add_page_numbers(str(src), str(Path(tmp_dir) / "n.pdf"),
                                   header="RAPPORT INTERNE", footer="Diffusion restreinte")
            text = _text_of(out, 0)
            self.assertIn("RAPPORT INTERNE", text)
            self.assertIn("Diffusion restreinte", text)

    def test_header_only_without_numbering(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=1)
            out = add_page_numbers(str(src), str(Path(tmp_dir) / "n.pdf"),
                                   number_format="", header="EN-TETE")
            self.assertIn("EN-TETE", _text_of(out))

    def test_unknown_position_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=1)
            with self.assertRaises(ValueError):
                add_page_numbers(str(src), str(Path(tmp_dir) / "n.pdf"),
                                 position="Au milieu")

    def test_invalid_format_is_refused_with_a_helpful_message(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=1)
            with self.assertRaises(ValueError) as ctx:
                add_page_numbers(str(src), str(Path(tmp_dir) / "n.pdf"),
                                 number_format="Page {numero}")
            self.assertIn("{n}", str(ctx.exception))

    def test_original_content_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=1)
            out = add_page_numbers(str(src), str(Path(tmp_dir) / "n.pdf"))
            self.assertIn("PAGE NUMERO 1", _text_of(out))


class TestProtectAndUnlock(unittest.TestCase):
    def test_protected_file_requires_the_password(self):
        import fitz

        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=3)
            out = protect_pdf(str(src), str(Path(tmp_dir) / "protege.pdf"), "MonMotDePasse")

            doc = fitz.open(out)
            try:
                self.assertTrue(doc.is_encrypted)
                self.assertFalse(doc.authenticate("mauvais"))
                self.assertTrue(doc.authenticate("MonMotDePasse"))
            finally:
                doc.close()

            with self.assertRaises(ValueError):
                page_count(out)                       # sans mot de passe
            self.assertEqual(page_count(out, password="MonMotDePasse"), 3)

    def test_empty_password_refused(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=1)
            with self.assertRaises(ValueError):
                protect_pdf(str(src), str(Path(tmp_dir) / "p.pdf"), "")

    def test_printing_permission_is_applied(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=1)
            allowed = protect_pdf(str(src), str(Path(tmp_dir) / "oui.pdf"), "pw",
                                  allow_printing=True)
            denied = protect_pdf(str(src), str(Path(tmp_dir) / "non.pdf"), "pw",
                                 allow_printing=False)
            self.assertTrue(Path(allowed).exists())
            self.assertTrue(Path(denied).exists())

    def test_reprotecting_an_already_protected_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plain, locked = Path(tmp_dir) / "a.pdf", Path(tmp_dir) / "b.pdf"
            _build_pdf(plain, pages=2)
            _encrypt(plain, locked)
            out = protect_pdf(str(locked), str(Path(tmp_dir) / "c.pdf"),
                              "nouveau", current_password="s3cret")
            self.assertEqual(page_count(out, password="nouveau"), 2)

    def test_reprotecting_with_wrong_current_password_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plain, locked = Path(tmp_dir) / "a.pdf", Path(tmp_dir) / "b.pdf"
            _build_pdf(plain, pages=1)
            _encrypt(plain, locked)
            with self.assertRaises(ValueError):
                protect_pdf(str(locked), str(Path(tmp_dir) / "c.pdf"),
                            "nouveau", current_password="faux")

    def test_unlock_removes_the_password(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plain, locked = Path(tmp_dir) / "a.pdf", Path(tmp_dir) / "b.pdf"
            _build_pdf(plain, pages=3)
            _encrypt(plain, locked)

            out = unlock_pdf(str(locked), str(Path(tmp_dir) / "ouvert.pdf"), "s3cret")
            self.assertEqual(page_count(out), 3)      # plus aucun mot de passe requis
            self.assertIn("PAGE NUMERO 1", _text_of(out))

    def test_unlock_with_wrong_password_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plain, locked = Path(tmp_dir) / "a.pdf", Path(tmp_dir) / "b.pdf"
            _build_pdf(plain, pages=1)
            _encrypt(plain, locked)
            with self.assertRaises(ValueError):
                unlock_pdf(str(locked), str(Path(tmp_dir) / "o.pdf"), "faux")

    def test_unlock_of_an_unprotected_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=1)
            with self.assertRaises(ValueError) as ctx:
                unlock_pdf(str(src), str(Path(tmp_dir) / "o.pdf"), "pw")
            self.assertIn("n'est pas protégé", str(ctx.exception))

    def test_merging_an_aes_protected_file_gives_a_clear_message(self):
        # Un PDF protégé par cet outil est chiffré en AES-256, que pypdf (utilisé
        # par la fusion) ne sait pas lire sans le paquet `cryptography`. Sans
        # rattrapage, l'utilisateur verrait une erreur de dépendance obscure.
        from core.pdf_merger import PdfItem, merge_pdfs

        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=2)
            protected = protect_pdf(str(src), str(Path(tmp_dir) / "p.pdf"), "abc")

            with self.assertRaises(ValueError) as ctx:
                merge_pdfs([PdfItem(protected)], str(Path(tmp_dir) / "m.pdf"))
            message = str(ctx.exception)
            self.assertIn("chiffrement fort", message)
            self.assertIn("Outils PDF", message)

    def test_protect_then_unlock_round_trip_preserves_pages(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.pdf"
            _build_pdf(src, pages=4)
            protected = protect_pdf(str(src), str(Path(tmp_dir) / "p.pdf"), "abc")
            opened = unlock_pdf(protected, str(Path(tmp_dir) / "o.pdf"), "abc")
            self.assertEqual(page_count(opened), 4)
            self.assertIn("PAGE NUMERO 4", _text_of(opened, 3))


if __name__ == "__main__":
    unittest.main()
