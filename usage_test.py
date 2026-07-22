import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

try:
    import yt_dlp  # noqa: F401
except ImportError:
    yt_dlp = types.ModuleType("yt_dlp")
    yt_dlp.YoutubeDL = lambda opts: None
    yt_dlp.utils = types.ModuleType("yt_dlp.utils")
    yt_dlp.utils.DownloadError = Exception
    sys.modules["yt_dlp"] = yt_dlp
    sys.modules["yt_dlp.utils"] = yt_dlp.utils

import utils.config as config_mod
import utils.helpers as helpers
from core.file_converter import convert_file, detect_category
from core.pdf_merger import PdfItem, merge_pdfs
from core.video_downloader import CancelledError, VideoDownloader


class TestHelpers(unittest.TestCase):
    def test_human_size(self):
        self.assertEqual(helpers.human_size(512), "512.0 B")
        self.assertEqual(helpers.human_size(1024 * 1.5), "1.5 KB")

    def test_format_duration(self):
        self.assertEqual(helpers.format_duration(0), "??:??")
        self.assertEqual(helpers.format_duration(59), "0:59")
        self.assertEqual(helpers.format_duration(61), "1:01")
        self.assertEqual(helpers.format_duration(3662), "1:01:02")

    def test_unique_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir) / "file.txt"
            base.write_text("content", encoding="utf-8")
            unique = helpers.unique_path(base)
            self.assertNotEqual(base, unique)
            self.assertEqual(unique.name, "file_1.txt")

    def test_parse_page_ranges(self):
        self.assertEqual(helpers.parse_page_ranges("", 5), [0, 1, 2, 3, 4])
        self.assertEqual(helpers.parse_page_ranges("1,3-4", 5), [0, 2, 3])
        with self.assertRaises(ValueError):
            helpers.parse_page_ranges("0-2", 4)
        with self.assertRaises(ValueError):
            helpers.parse_page_ranges("3-2", 4)
        with self.assertRaises(ValueError):
            helpers.parse_page_ranges("1,10", 4)


class TestConfig(unittest.TestCase):
    def test_load_config_returns_default_when_missing(self):
        with patch.object(config_mod, "CONFIG_FILE", Path(tempfile.gettempdir()) / "no_such_config.json"):
            loaded = config_mod.load_config()
        self.assertEqual(loaded["theme"], config_mod.DEFAULT_CONFIG["theme"])
        self.assertEqual(loaded["language"], config_mod.DEFAULT_CONFIG["language"])

    def test_save_and_load_config(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_file = Path(tmp_dir) / "config.json"
            with patch.object(config_mod, "CONFIG_FILE", config_file), patch.object(config_mod, "CONFIG_DIR", Path(tmp_dir)):
                config_mod.save_config({"theme": "light", "language": "fr", "output_dir": str(Path(tmp_dir) / "out")})
                loaded = config_mod.load_config()
        self.assertEqual(loaded["theme"], "light")
        self.assertEqual(loaded["language"], "fr")


class TestFileConverter(unittest.TestCase):
    def test_detect_category(self):
        self.assertEqual(detect_category("photo.JPG"), "image")
        self.assertEqual(detect_category("video.mp4"), "video")
        self.assertEqual(detect_category("audio.MP3"), "audio")
        self.assertEqual(detect_category("document.docx"), "document")
        self.assertEqual(detect_category("tableur.csv"), "sheet")
        self.assertEqual(detect_category("archive.zip"), "archive")
        self.assertEqual(detect_category("fichier.pdf"), "pdf")
        self.assertIsNone(detect_category("fichier.unknown"))

    def test_convert_text_to_pdf(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "sample.txt"
            src.write_text("Bonjour\nTest\n", encoding="utf-8")
            out = convert_file(str(src), "PDF", tmp_dir)
            self.assertEqual(Path(out).suffix.lower(), ".pdf")
            self.assertTrue(Path(out).exists())

    def test_convert_image_png_to_jpg(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow non installé")

        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "image.png"
            Image.new("RGB", (16, 16), "blue").save(src)
            out = convert_file(str(src), "JPG", tmp_dir)
            self.assertEqual(Path(out).suffix.lower(), ".jpg")
            self.assertTrue(Path(out).exists())

    def test_convert_sheet_csv_to_xlsx_and_back(self):
        try:
            import pandas as pd
        except ImportError:
            self.skipTest("Pandas non installé")

        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "data.csv"
            csv_file.write_text("col1,col2\n1,2\n3,4\n", encoding="utf-8")
            xlsx_path = convert_file(str(csv_file), "XLSX", tmp_dir)
            self.assertEqual(Path(xlsx_path).suffix.lower(), ".xlsx")
            self.assertTrue(Path(xlsx_path).exists())

            csv_path = convert_file(str(xlsx_path), "CSV", tmp_dir)
            self.assertEqual(Path(csv_path).suffix.lower(), ".csv")
            self.assertTrue(Path(csv_path).exists())

    def test_convert_media_without_ffmpeg_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dummy_video = Path(tmp_dir) / "sample.mp4"
            dummy_video.write_bytes(b"")
            with patch("core.file_converter.get_ffmpeg_path", return_value=None):
                with self.assertRaises(RuntimeError):
                    convert_file(str(dummy_video), "mp3", tmp_dir)

    def test_convert_pdf_to_images_if_pymupdf_available(self):
        try:
            import fitz
        except ImportError:
            self.skipTest("PyMuPDF non installé")

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab non installé")

        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_file = Path(tmp_dir) / "sample.pdf"
            c = canvas.Canvas(str(pdf_file), pagesize=A4)
            c.drawString(100, 750, "Test")
            c.save()
            out = convert_file(str(pdf_file), "JPG", tmp_dir)
            self.assertTrue(Path(out).exists())
            self.assertIn(Path(out).suffix.lower(), {".jpg", ".png"})

    def test_archive_handling_zip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "file.txt"
            src.write_text("archive test", encoding="utf-8")
            zip_path = Path(tmp_dir) / "archive.zip"
            import zipfile

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(src, src.name)

            extracted = convert_file(str(zip_path), "EXTRAIRE", tmp_dir)
            self.assertTrue(Path(extracted).is_dir())
            self.assertTrue((Path(extracted) / "file.txt").exists())

            # "ZIP" comme cible n'est routé vers la recompression que pour les
            # fichiers de catégorie "archive" (dispatch par extension) : on
            # réutilise donc zip_path, pas le .txt d'origine (catégorie "document").
            zipped = convert_file(str(zip_path), "ZIP", tmp_dir)
            self.assertEqual(Path(zipped).suffix.lower(), ".zip")
            self.assertTrue(Path(zipped).exists())

    def test_convert_file_unknown_extension_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "unknown.ext"
            src.write_text("data", encoding="utf-8")
            with self.assertRaises(ValueError):
                convert_file(str(src), "TXT", tmp_dir)


class TestPdfMerger(unittest.TestCase):
    def _build_pdf(self, path: Path, text: str):
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
        except ImportError:
            self.skipTest("reportlab non installé")

        c = canvas.Canvas(str(path), pagesize=A4)
        c.drawString(100, 750, text)
        c.showPage()
        c.save()

    def test_merge_pdfs_empty_list_raises(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "result.pdf"
            with self.assertRaises(ValueError):
                merge_pdfs([], str(out_file))

    def test_merge_pdfs_creates_output(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf1 = Path(tmp_dir) / "a.pdf"
            pdf2 = Path(tmp_dir) / "b.pdf"
            self._build_pdf(pdf1, "Page A")
            self._build_pdf(pdf2, "Page B")
            items = [PdfItem(str(pdf1)), PdfItem(str(pdf2), page_range="1")] 
            out_file = Path(tmp_dir) / "merged.pdf"
            result = merge_pdfs(items, str(out_file))
            self.assertEqual(result, str(out_file))
            self.assertTrue(out_file.exists())
            from pypdf import PdfReader

            reader = PdfReader(result)
            self.assertEqual(len(reader.pages), 2)

    def test_merge_pdfs_progress_callback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf1 = Path(tmp_dir) / "a.pdf"
            pdf2 = Path(tmp_dir) / "b.pdf"
            self._build_pdf(pdf1, "Page A")
            self._build_pdf(pdf2, "Page B")
            messages = []

            def callback(progress, message):
                messages.append((progress, message))

            out_file = Path(tmp_dir) / "merged.pdf"
            merge_pdfs([PdfItem(str(pdf1)), PdfItem(str(pdf2))], str(out_file), progress_callback=callback)
            self.assertEqual(messages[-1][0], 1.0)
            self.assertIn("Fusion terminée", messages[-1][1])


class TestVideoDownloader(unittest.TestCase):
    def test_cancel_sets_cancelled_event(self):
        downloader = VideoDownloader()
        downloader.cancel()
        self.assertTrue(downloader._cancel_event.is_set())

    def test_fetch_info_uses_yt_dlp(self):
        fake_info = {"title": "Titre de test", "duration": 123, "uploader": "Auteur"}
        ydl_instance = MagicMock()
        ydl_instance.extract_info.return_value = fake_info
        ydl_context = MagicMock(__enter__=MagicMock(return_value=ydl_instance), __exit__=MagicMock(return_value=None))

        with patch("core.video_downloader.yt_dlp.YoutubeDL", return_value=ydl_context):
            info = VideoDownloader.fetch_info("https://example.com")
        self.assertEqual(info["title"], "Titre de test")
        self.assertEqual(info["duration"], 123)
        self.assertEqual(info["uploader"], "Auteur")

    def test_download_returns_filename_for_mp4(self):
        ydl_instance = MagicMock()
        ydl_instance.extract_info.return_value = {"title": "video", "ext": "mp4"}
        ydl_instance.prepare_filename.return_value = "video.mp4"
        ydl_context = MagicMock(__enter__=MagicMock(return_value=ydl_instance), __exit__=MagicMock(return_value=None))

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("core.video_downloader.yt_dlp.YoutubeDL", return_value=ydl_context), patch("core.video_downloader.get_ffmpeg_path", return_value=str(Path(tmp_dir) / "ffmpeg")):
                out_path = VideoDownloader().download("https://example.com", tmp_dir, fmt="mp4")
        self.assertTrue(out_path.endswith(".mp4"))

    def test_download_raises_cancelled_error_when_cancelled(self):
        ydl_instance = MagicMock()
        ydl_instance.extract_info.side_effect = CancelledError("Téléchargement annulé.")
        ydl_context = MagicMock(__enter__=MagicMock(return_value=ydl_instance), __exit__=MagicMock(return_value=None))

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("core.video_downloader.yt_dlp.YoutubeDL", return_value=ydl_context), patch("core.video_downloader.get_ffmpeg_path", return_value="/usr/bin/ffmpeg"):
                downloader = VideoDownloader()
                downloader.cancel()
                with self.assertRaises(CancelledError):
                    downloader.download("https://example.com", tmp_dir, fmt="mp4")


if __name__ == "__main__":
    unittest.main()
