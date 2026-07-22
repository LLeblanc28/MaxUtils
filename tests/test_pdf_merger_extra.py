"""Couvre PdfItem.num_pages (jamais appelée directement dans usage_test.py)
et la branche de rotation de merge_pdfs."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pdf_merger import PdfItem, merge_pdfs


def _build_pdf(path: Path, text: str) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawString(100, 750, text)
    c.showPage()
    c.save()


class TestPdfItemNumPages(unittest.TestCase):
    def test_num_pages_reads_and_caches(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "a.pdf"
            _build_pdf(pdf_path, "Page A")
            item = PdfItem(str(pdf_path))
            self.assertEqual(item.num_pages, 1)
            # Deuxième accès : valeur mise en cache, pas de relecture disque.
            self.assertEqual(item.num_pages, 1)


class TestMergeRotation(unittest.TestCase):
    def test_merge_applies_rotation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "a.pdf"
            _build_pdf(pdf_path, "Page A")
            out_file = Path(tmp_dir) / "merged.pdf"
            item = PdfItem(str(pdf_path), rotation=90)
            result = merge_pdfs([item], str(out_file))

            from pypdf import PdfReader
            reader = PdfReader(result)
            self.assertEqual(reader.pages[0].rotation, 90)


if __name__ == "__main__":
    unittest.main()
