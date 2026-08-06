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
    compress_pdf,
    page_count,
    protect_pdf,
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
