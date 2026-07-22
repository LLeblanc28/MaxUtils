"""Tests de la suite de correctifs de sécurité (audit MultiToolApp).

Chaque classe correspond à un identifiant du rapport d'audit. Pour les
protections destructrices (Zip Slip, PDF chiffré), un cas légitime est
systématiquement vérifié en plus du cas malveillant : une protection qui
bloque tout n'est pas une protection.
"""

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.file_converter import convert_file
from core.pdf_merger import PdfItem, merge_pdfs
from utils.config import _validate_config
from utils.security import (
    SecurityError,
    check_file_size,
    ensure_within_directory,
    sanitize_filename,
    validate_url,
    verify_file_signature,
)


class TestValidateUrlH01(unittest.TestCase):
    def test_valid_https_url_accepted(self):
        validate_url("https://www.youtube.com/watch?v=abc123")  # ne doit pas lever

    def test_valid_http_url_accepted(self):
        validate_url("http://example.com/video")  # ne doit pas lever

    def test_file_scheme_blocked(self):
        with self.assertRaises(SecurityError):
            validate_url("file:///C:/Windows/System32/config/SAM")

    def test_localhost_blocked(self):
        with self.assertRaises(SecurityError):
            validate_url("http://localhost/admin")

    def test_loopback_ip_blocked(self):
        with self.assertRaises(SecurityError):
            validate_url("http://127.0.0.1:8080/")

    def test_cloud_metadata_link_local_blocked(self):
        with self.assertRaises(SecurityError):
            validate_url("http://169.254.169.254/latest/meta-data/")

    def test_private_ip_range_blocked(self):
        for ip in ("192.168.1.1", "10.0.0.5", "172.16.0.1"):
            with self.assertRaises(SecurityError):
                validate_url(f"http://{ip}/")

    def test_public_ip_allowed(self):
        validate_url("http://8.8.8.8/")  # ne doit pas lever

    def test_empty_url_blocked(self):
        with self.assertRaises(SecurityError):
            validate_url("")

    def test_oversized_url_blocked(self):
        with self.assertRaises(SecurityError):
            validate_url("https://example.com/" + "a" * 3000)

    def test_ftp_scheme_blocked(self):
        with self.assertRaises(SecurityError):
            validate_url("ftp://example.com/file")


class TestSanitizeFilename(unittest.TestCase):
    def test_strips_path_separators(self):
        self.assertNotIn("/", sanitize_filename("../../evil"))
        self.assertNotIn("\\", sanitize_filename("..\\..\\evil"))

    def test_keeps_accented_characters(self):
        self.assertEqual(sanitize_filename("Vidéo été"), "Vidéo été")

    def test_empty_falls_back(self):
        self.assertEqual(sanitize_filename("///???"), "fichier")

    def test_length_capped(self):
        self.assertLessEqual(len(sanitize_filename("a" * 500, max_length=50)), 50)


class TestEnsureWithinDirectoryC01(unittest.TestCase):
    def test_subpath_allowed(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            sub = Path(tmp_dir) / "video.mp4"
            result = ensure_within_directory(str(sub), tmp_dir)
            self.assertEqual(result, sub.resolve())

    def test_parent_escape_blocked(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            escape = Path(tmp_dir) / ".." / "evil.mp4"
            with self.assertRaises(SecurityError):
                ensure_within_directory(str(escape), tmp_dir)

    def test_absolute_escape_blocked(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(SecurityError):
                ensure_within_directory("C:/Windows/System32/evil.exe", tmp_dir)


class TestCheckFileSize(unittest.TestCase):
    def test_small_file_passes(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f = Path(tmp_dir) / "small.txt"
            f.write_text("hello")
            check_file_size(str(f), max_bytes=1024)

    def test_oversized_file_blocked(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f = Path(tmp_dir) / "big.txt"
            f.write_bytes(b"x" * 2048)
            with self.assertRaises(SecurityError):
                check_file_size(str(f), max_bytes=1024)


class TestVerifyFileSignature(unittest.TestCase):
    def test_real_png_accepted(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f = Path(tmp_dir) / "img.png"
            f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
            self.assertTrue(verify_file_signature(str(f)))

    def test_fake_jpg_with_exe_header_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f = Path(tmp_dir) / "fake.jpg"
            f.write_bytes(b"MZ\x90\x00" + b"\x00" * 20)  # en-tête PE (.exe)
            self.assertFalse(verify_file_signature(str(f)))

    def test_unknown_container_format_not_blocked(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f = Path(tmp_dir) / "video.mp4"
            f.write_bytes(b"\x00\x00\x00\x18ftypmp42")
            self.assertTrue(verify_file_signature(str(f)))


class TestZipSlipC02(unittest.TestCase):
    def test_malicious_zip_blocked(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_path = Path(tmp_dir) / "evil.zip"
            with zipfile.ZipFile(zip_path, "w") as z:
                z.writestr("../../../../tmp/PWNED.txt", "pwned")
            escape_target = Path(tmp_dir).parent.parent.parent.parent / "tmp" / "PWNED.txt"
            with self.assertRaises(SecurityError):
                convert_file(str(zip_path), "EXTRAIRE", tmp_dir)
            self.assertFalse(escape_target.exists())

    def test_legitimate_zip_still_extracts(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "file.txt"
            src.write_text("contenu légitime", encoding="utf-8")
            zip_path = Path(tmp_dir) / "archive.zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(src, src.name)

            extracted = convert_file(str(zip_path), "EXTRAIRE", tmp_dir)
            self.assertTrue((Path(extracted) / "file.txt").exists())


class TestConfigValidationM04(unittest.TestCase):
    def test_injected_key_ignored(self):
        result = _validate_config({"theme": "dark", "__proto__": "evil", "extra_key": 123})
        self.assertNotIn("__proto__", result)
        self.assertNotIn("extra_key", result)

    def test_invalid_theme_falls_back_to_default(self):
        result = _validate_config({"theme": "'; DROP TABLE users;--"})
        self.assertEqual(result["theme"], "dark")

    def test_valid_override_kept(self):
        result = _validate_config({"theme": "light", "language": "en"})
        self.assertEqual(result["theme"], "light")
        self.assertEqual(result["language"], "en")

    def test_non_dict_input_returns_defaults(self):
        result = _validate_config("not a dict")
        self.assertEqual(result["theme"], "dark")


class TestPdfEncryptedH02(unittest.TestCase):
    def _build_pdf(self, path: Path):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab non installé")
        c = canvas.Canvas(str(path), pagesize=A4)
        c.drawString(100, 750, "Contenu")
        c.showPage()
        c.save()

    def test_password_protected_pdf_raises_clear_error(self):
        try:
            from pypdf import PdfReader, PdfWriter
        except ImportError:
            self.skipTest("pypdf non installé")

        with tempfile.TemporaryDirectory() as tmp_dir:
            plain = Path(tmp_dir) / "plain.pdf"
            self._build_pdf(plain)

            encrypted = Path(tmp_dir) / "encrypted.pdf"
            writer = PdfWriter()
            for page in PdfReader(str(plain)).pages:
                writer.add_page(page)
            writer.encrypt("s3cret")
            with open(encrypted, "wb") as f:
                writer.write(f)

            out_file = Path(tmp_dir) / "merged.pdf"
            with self.assertRaises(ValueError):
                merge_pdfs([PdfItem(str(encrypted))], str(out_file))

    def test_unencrypted_pdf_merges_normally(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf1 = Path(tmp_dir) / "a.pdf"
            self._build_pdf(pdf1)
            out_file = Path(tmp_dir) / "merged.pdf"
            result = merge_pdfs([PdfItem(str(pdf1))], str(out_file))
            self.assertTrue(Path(result).exists())


if __name__ == "__main__":
    unittest.main()
