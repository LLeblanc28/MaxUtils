"""Tests complémentaires pour couvrir les branches de core/file_converter.py
non exercées par usage_test.py (HEIC, media réel, docx, PDF multi-page,
archives 7z/tar.gz, cas d'erreur)."""

import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import file_converter
from core.file_converter import _handle_archive, _safe_extract_zip, convert_file
from utils.security import SecurityError


class TestConvertImageHeicAndRgba(unittest.TestCase):
    def test_heic_import_error_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "photo.heic"
            src.write_bytes(b"not a real heic file")
            with patch.dict(sys.modules, {"pillow_heif": None}):
                with self.assertRaises(RuntimeError):
                    convert_file(str(src), "jpg", tmp_dir)

    def test_heic_registers_opener_before_failing_on_garbage_bytes(self):
        # pillow_heif est installé : l'import/register réussit (couvre le
        # bloc try), puis Image.open échoue sur les octets invalides.
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "photo.heic"
            src.write_bytes(b"not a real heic file")
            with self.assertRaises(Exception):
                convert_file(str(src), "jpg", tmp_dir)

    def test_rgba_png_converted_to_jpg_forces_rgb(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "image.png"
            Image.new("RGBA", (8, 8), (10, 20, 30, 128)).save(src)
            out = convert_file(str(src), "JPG", tmp_dir)
            self.assertTrue(Path(out).exists())
            with Image.open(out) as result:
                self.assertEqual(result.mode, "RGB")


class TestConvertMedia(unittest.TestCase):
    def test_convert_media_mp3_success_with_progress_callback(self):
        calls = []
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "clip.mp4"
            src.write_bytes(b"\x00")
            with patch.object(file_converter, "get_ffmpeg_path", return_value="ffmpeg"), \
                 patch.object(file_converter.subprocess, "run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                out = convert_file(str(src), "mp3", tmp_dir, cb=lambda p, m: calls.append((p, m)))
        self.assertTrue(out.endswith(".mp3"))
        self.assertEqual(calls[0][0], 0.1)
        self.assertEqual(calls[-1][0], 1.0)

    def test_convert_media_gif_target_without_callback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "clip.mp4"
            src.write_bytes(b"\x00")
            with patch.object(file_converter, "get_ffmpeg_path", return_value="ffmpeg"), \
                 patch.object(file_converter.subprocess, "run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stderr="")
                out = convert_file(str(src), "gif", tmp_dir)
        self.assertTrue(out.endswith(".gif"))

    def test_convert_media_ffmpeg_failure_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "clip.mp4"
            src.write_bytes(b"\x00")
            with patch.object(file_converter, "get_ffmpeg_path", return_value="ffmpeg"), \
                 patch.object(file_converter.subprocess, "run") as mock_run:
                mock_run.return_value = MagicMock(returncode=1, stderr="erreur ffmpeg")
                with self.assertRaises(RuntimeError):
                    convert_file(str(src), "mp4", tmp_dir)


class TestConvertDocument(unittest.TestCase):
    def test_docx_conversion_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.docx"
            src.write_bytes(b"fake docx")

            def fake_convert(source, out):
                Path(out).write_bytes(b"%PDF-1.4 fake")

            with patch("docx2pdf.convert", side_effect=fake_convert):
                out = convert_file(str(src), "pdf", tmp_dir)
            self.assertTrue(Path(out).exists())
            self.assertEqual(Path(out).suffix.lower(), ".pdf")

    def test_docx_conversion_failure_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "doc.docx"
            src.write_bytes(b"fake docx")
            with patch("docx2pdf.convert", side_effect=RuntimeError("Word absent")):
                with self.assertRaises(RuntimeError):
                    convert_file(str(src), "pdf", tmp_dir)

    def test_txt_to_pdf_spans_multiple_pages(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "long.txt"
            src.write_text("\n".join(f"ligne {i}" for i in range(200)), encoding="utf-8")
            out = convert_file(str(src), "pdf", tmp_dir)
            self.assertTrue(Path(out).exists())

            from pypdf import PdfReader
            self.assertGreater(len(PdfReader(out).pages), 1)


class TestConvertSheet(unittest.TestCase):
    def test_unsupported_sheet_conversion_raises_value_error(self):
        try:
            import pandas  # noqa: F401
        except ImportError:
            self.skipTest("pandas non installé")
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "data.csv"
            src.write_text("a,b\n1,2\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                convert_file(str(src), "csv", tmp_dir)


class TestConvertPdfToImagesMultiPage(unittest.TestCase):
    def test_multi_page_pdf_produces_folder_of_images(self):
        try:
            import fitz  # noqa: F401
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("PyMuPDF/reportlab non installés")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_file = Path(tmp_dir) / "multi.pdf"
            c = canvas.Canvas(str(pdf_file), pagesize=A4)
            for i in range(3):
                c.drawString(100, 750, f"Page {i}")
                c.showPage()
            c.save()

            calls = []
            out = convert_file(str(pdf_file), "png", tmp_dir, cb=lambda p, m: calls.append((p, m)))
            self.assertTrue(Path(out).is_dir())
            self.assertEqual(len(list(Path(out).glob("*.png"))), 3)
            self.assertEqual(calls[-1][0], 1.0)

    def test_pymupdf_import_error_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas

            pdf_file = Path(tmp_dir) / "sample.pdf"
            canvas.Canvas(str(pdf_file), pagesize=A4).save()
            with patch.dict(sys.modules, {"fitz": None}):
                with self.assertRaises(RuntimeError):
                    convert_file(str(pdf_file), "jpg", tmp_dir)


class TestArchiveEdgeCases(unittest.TestCase):
    def test_zip_symlink_entry_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = Path(tmp_dir) / "symlink.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                info = zipfile.ZipInfo("link")
                info.external_attr = (0xA1FF) << 16  # S_IFLNK | 0777
                z.writestr(info, "/etc/passwd")
            with self.assertRaises(SecurityError):
                convert_file(str(zip_path), "EXTRAIRE", tmp_dir)

    def test_decompression_bomb_rejected(self):
        # Passe la limite en paramètre plutôt que de monkeypatcher la constante
        # de module : plus robuste (évite tout aléa d'ordre d'exécution) et
        # exerce directement _safe_extract_zip, qui porte cette logique.
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = Path(tmp_dir) / "bomb.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("a.txt", "x" * 1000)
            dest = Path(tmp_dir) / "out"
            dest.mkdir()
            with self.assertRaises(SecurityError):
                _safe_extract_zip(str(zip_path), dest, max_extracted_size=10)

    def test_7z_archive_extracts_successfully(self):
        try:
            import py7zr
        except ImportError:
            self.skipTest("py7zr non installé")

        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "file.txt"
            src.write_text("contenu 7z", encoding="utf-8")
            archive_path = Path(tmp_dir) / "archive.7z"
            with py7zr.SevenZipFile(archive_path, "w") as z:
                z.write(str(src), "file.txt")

            extracted = convert_file(str(archive_path), "EXTRAIRE", tmp_dir)
            self.assertTrue((Path(extracted) / "file.txt").exists())

    def test_7z_import_error_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            archive_path = Path(tmp_dir) / "archive.7z"
            archive_path.write_bytes(b"7z\xbc\xaf\x27\x1c")
            with patch.dict(sys.modules, {"py7zr": None}):
                with self.assertRaises(RuntimeError):
                    convert_file(str(archive_path), "EXTRAIRE", tmp_dir)

    def test_tar_gz_archive_extracts_successfully(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "file.txt"
            src.write_text("contenu tar", encoding="utf-8")
            archive_path = Path(tmp_dir) / "archive.tar.gz"
            with tarfile.open(archive_path, "w:gz") as t:
                t.add(str(src), arcname="file.txt")

            extracted = convert_file(str(archive_path), "EXTRAIRE", tmp_dir)
            self.assertTrue((Path(extracted) / "file.txt").exists())

    def test_unsupported_archive_extension_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            fake = Path(tmp_dir) / "archive.rar"
            fake.write_bytes(b"fake rar")
            with self.assertRaises(ValueError):
                _handle_archive(str(fake), "extraire", tmp_dir)


if __name__ == "__main__":
    unittest.main()
