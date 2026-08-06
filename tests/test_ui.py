"""Tests de l'interface graphique (customtkinter réel, sans mainloop).

Techniques utilisées pour rendre le code UI testable de façon déterministe :
- `threading.Thread` est remplacé par une version synchrone (le worker
  s'exécute immédiatement dans le thread de test, pas de vrai thread).
- `.after(ms, fn, ...)` est monkeypatché par instance pour appeler `fn`
  immédiatement, au lieu d'attendre une boucle d'événements Tk.
- Les boîtes de dialogue (`filedialog.*`) sont toujours mockées : jamais de
  vraie fenêtre de sélection de fichier ouverte pendant les tests.
- Les callbacks de widgets customtkinter (`CTkButton`, `CTkOptionMenu`) sont
  invoqués directement via leur attribut interne `_command`, plutôt que par
  simulation de clic — customtkinter les stocke tel quel (cf. code source).
"""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk

from ui.widgets import LogBox
from utils.security import SecurityError


class _SyncThread:
    """Remplace threading.Thread : exécute la cible immédiatement, sans thread réel."""

    def __init__(self, target=None, daemon=None, args=(), kwargs=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)

    def join(self, *a, **kw):
        pass


def _sync_after(widget):
    widget.after = lambda ms, fn=None, *a, **kw: (fn(*a, **kw) if fn else None)


def _find_all(widget, cls):
    found = []
    for child in widget.winfo_children():
        if isinstance(child, cls):
            found.append(child)
        found.extend(_find_all(child, cls))
    return found


def _find_by_text(widget, cls, text):
    return [w for w in _find_all(widget, cls) if w.cget("text") == text]


def _build_pdf(path: Path, text: str = "Page") -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawString(100, 750, text)
    c.showPage()
    c.save()


class _TkTestCase(unittest.TestCase):
    """Base commune : une seule racine Tk cachée partagée par classe de tests."""

    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.thread_patcher = patch("threading.Thread", _SyncThread)
        self.thread_patcher.start()

    def tearDown(self):
        self.thread_patcher.stop()


class TestLogBox(_TkTestCase):
    def test_log_appends_colored_line(self):
        box = LogBox(self.root)
        _sync_after(box)
        box.log("Un message", "success")
        content = box.text.get("1.0", "end")
        self.assertIn("Un message", content)
        box.destroy()

    def test_log_default_level_is_info(self):
        box = LogBox(self.root)
        _sync_after(box)
        box.log("Sans niveau précisé")
        self.assertIn("Sans niveau précisé", box.text.get("1.0", "end"))
        box.destroy()


class TestVideoTab(_TkTestCase):
    def setUp(self):
        super().setUp()
        from ui.tab_video import VideoTab

        self.app = SimpleNamespace(config_data={"output_dir": tempfile.gettempdir()})
        self.tab = VideoTab(self.root, self.app)
        _sync_after(self.tab)
        _sync_after(self.tab.logbox)

    def tearDown(self):
        self.tab.destroy()
        super().tearDown()

    def test_on_format_change_toggles_widgets(self):
        self.tab.format_var.set("mp3")
        self.tab._on_format_change()
        self.assertTrue(self.tab.bitrate_menu.grid_info())
        self.assertFalse(self.tab.quality_menu.grid_info())

        self.tab.format_var.set("mp4")
        self.tab._on_format_change()
        self.assertTrue(self.tab.quality_menu.grid_info())
        self.assertFalse(self.tab.bitrate_menu.grid_info())

    def test_browse_updates_destination_when_folder_chosen(self):
        with patch("ui.tab_video.filedialog.askdirectory", return_value="D:/videos"):
            self.tab._browse()
        self.assertEqual(self.tab.dest_entry.get(), "D:/videos")

    def test_browse_keeps_destination_when_dialog_cancelled(self):
        before = self.tab.dest_entry.get()
        with patch("ui.tab_video.filedialog.askdirectory", return_value=""):
            self.tab._browse()
        self.assertEqual(self.tab.dest_entry.get(), before)

    def test_fetch_info_empty_url_logs_error(self):
        self.tab.url_entry.insert(0, "")
        self.tab._fetch_info()
        self.assertIn("saisir une URL", self.tab.logbox.text.get("1.0", "end"))

    def test_fetch_info_rejected_url_logs_security_error(self):
        self.tab.url_entry.insert(0, "file:///etc/passwd")
        self.tab._fetch_info()
        self.assertIn("URL refusée", self.tab.logbox.text.get("1.0", "end"))

    def test_fetch_info_success_updates_label(self):
        self.tab.url_entry.insert(0, "https://example.com/watch")
        fake_info = {"title": "Ma vidéo", "duration": 90, "uploader": "x"}
        with patch("ui.tab_video.VideoDownloader.fetch_info", return_value=fake_info):
            self.tab._fetch_info()
        self.assertIn("Ma vidéo", self.tab.info_label.cget("text"))

    def test_fetch_info_worker_security_error_logged(self):
        self.tab.url_entry.insert(0, "https://example.com/watch")
        with patch("ui.tab_video.VideoDownloader.fetch_info", side_effect=SecurityError("bloqué")):
            self.tab._fetch_info()
        self.assertIn("URL refusée", self.tab.logbox.text.get("1.0", "end"))

    def test_fetch_info_worker_generic_error_logged(self):
        self.tab.url_entry.insert(0, "https://example.com/watch")
        with patch("ui.tab_video.VideoDownloader.fetch_info", side_effect=RuntimeError("boom")):
            self.tab._fetch_info()
        self.assertIn("Erreur :", self.tab.logbox.text.get("1.0", "end"))

    def test_start_download_empty_url_logs_error(self):
        self.tab.url_entry.insert(0, "")
        self.tab._start_download()
        self.assertIn("saisir une URL", self.tab.logbox.text.get("1.0", "end"))

    def test_start_download_rejected_url_logs_security_error(self):
        self.tab.url_entry.insert(0, "http://127.0.0.1/")
        self.tab._start_download()
        self.assertIn("URL refusée", self.tab.logbox.text.get("1.0", "end"))

    def test_start_download_success_with_progress(self):
        self.tab.url_entry.insert(0, "https://example.com/watch")

        def fake_download(url, dest, fmt, quality, bitrate, progress_callback,
                          playlist=False, subtitles="", start="", end=""):
            progress_callback({"percent": 0.5, "speed": 1024, "eta": 3})
            progress_callback({"percent": 1.0, "speed": None, "eta": None})
            return [str(Path(dest) / "video.mp4")]

        with patch.object(self.tab.downloader, "download", side_effect=fake_download):
            self.tab._start_download()
        text = self.tab.logbox.text.get("1.0", "end")
        self.assertIn("Terminé", text)
        self.assertEqual(self.tab.dl_btn.cget("state"), "normal")

    def test_playlist_download_reports_a_file_count(self):
        self.tab.url_entry.insert(0, "https://example.com/playlist")
        self.tab.playlist_var.set(True)

        def fake_download(url, dest, fmt, quality, bitrate, progress_callback,
                          playlist=False, subtitles="", start="", end=""):
            return [f"{dest}/1.mp4", f"{dest}/2.mp4", f"{dest}/3.mp4"]

        with patch.object(self.tab.downloader, "download", side_effect=fake_download):
            self.tab._start_download()
        self.assertIn("3 fichiers", self.tab.logbox.text.get("1.0", "end"))

    def test_advanced_options_are_passed_to_the_downloader(self):
        self.tab.url_entry.insert(0, "https://example.com/watch")
        self.tab.playlist_var.set(True)
        self.tab.subtitle_menu.set("Français")
        self.tab.start_entry.insert(0, "1:20")
        self.tab.end_entry.insert(0, "3:45")
        captured = {}

        def fake_download(url, dest, fmt, quality, bitrate, progress_callback,
                          playlist=False, subtitles="", start="", end=""):
            captured.update(playlist=playlist, subtitles=subtitles, start=start, end=end)
            return [f"{dest}/video.mp4"]

        with patch.object(self.tab.downloader, "download", side_effect=fake_download):
            self.tab._start_download()

        self.assertTrue(captured["playlist"])
        self.assertEqual(captured["subtitles"], "fr")
        self.assertEqual(captured["start"], "1:20")
        self.assertEqual(captured["end"], "3:45")

    def test_enqueue_adds_and_clears_the_field(self):
        self.tab.url_entry.insert(0, "https://example.com/a")
        self.tab._enqueue()
        self.assertEqual(self.tab.queue, ["https://example.com/a"])
        self.assertEqual(self.tab.url_entry.get(), "")
        self.assertIn("File d'attente : 1", self.tab.queue_label.cget("text"))

    def test_enqueue_refuses_an_empty_or_unsafe_url(self):
        self.tab._enqueue()
        self.assertEqual(self.tab.queue, [])
        self.tab.url_entry.insert(0, "file:///etc/passwd")
        self.tab._enqueue()
        self.assertEqual(self.tab.queue, [])
        self.assertIn("URL refusée", self.tab.logbox.text.get("1.0", "end"))

    def test_enqueue_refuses_a_duplicate(self):
        for _ in range(2):
            self.tab.url_entry.delete(0, "end")
            self.tab.url_entry.insert(0, "https://example.com/a")
            self.tab._enqueue()
        self.assertEqual(len(self.tab.queue), 1)
        self.assertIn("déjà dans la file", self.tab.logbox.text.get("1.0", "end"))

    def test_clearing_the_queue_hides_its_label(self):
        self.tab.url_entry.insert(0, "https://example.com/a")
        self.tab._enqueue()
        self.tab._clear_queue()
        self.assertEqual(self.tab.queue, [])
        self.assertEqual(self.tab.queue_label.cget("text"), "")

    def test_queue_is_downloaded_in_order_then_emptied(self):
        for url in ("https://example.com/a", "https://example.com/b"):
            self.tab.url_entry.delete(0, "end")
            self.tab.url_entry.insert(0, url)
            self.tab._enqueue()

        seen = []

        def fake_download(url, dest, *a, **kw):
            seen.append(url)
            return [f"{dest}/{len(seen)}.mp4"]

        with patch.object(self.tab.downloader, "download", side_effect=fake_download):
            self.tab._start_download()

        self.assertEqual(seen, ["https://example.com/a", "https://example.com/b"])
        self.assertIn("File terminée : 2", self.tab.logbox.text.get("1.0", "end"))
        self.assertEqual(self.tab.queue, [])

    def test_url_left_in_the_field_is_appended_to_the_queue(self):
        # Une adresse saisie mais pas encore mise à la file ne doit pas être
        # perdue au moment de lancer le téléchargement.
        self.tab.url_entry.insert(0, "https://example.com/a")
        self.tab._enqueue()
        self.tab.url_entry.insert(0, "https://example.com/oubliee")

        seen = []
        with patch.object(self.tab.downloader, "download",
                          side_effect=lambda url, dest, *a, **kw: seen.append(url) or ["x.mp4"]):
            self.tab._start_download()
        self.assertEqual(seen, ["https://example.com/a", "https://example.com/oubliee"])

    def test_a_failing_url_does_not_stop_the_queue(self):
        for url in ("https://example.com/ko", "https://example.com/ok"):
            self.tab.url_entry.delete(0, "end")
            self.tab.url_entry.insert(0, url)
            self.tab._enqueue()

        def fake_download(url, dest, *a, **kw):
            if url.endswith("ko"):
                raise RuntimeError("vidéo indisponible")
            return [f"{dest}/ok.mp4"]

        with patch.object(self.tab.downloader, "download", side_effect=fake_download):
            self.tab._start_download()

        text = self.tab.logbox.text.get("1.0", "end")
        self.assertIn("vidéo indisponible", text)
        self.assertIn("File terminée : 1", text)   # la seconde a bien abouti

    def test_a_security_error_in_the_queue_is_reported_and_skipped(self):
        for url in ("https://example.com/a", "https://example.com/b"):
            self.tab.url_entry.delete(0, "end")
            self.tab.url_entry.insert(0, url)
            self.tab._enqueue()

        def fake_download(url, dest, *a, **kw):
            if url.endswith("a"):
                raise SecurityError("chemin refusé")
            return [f"{dest}/b.mp4"]

        with patch.object(self.tab.downloader, "download", side_effect=fake_download):
            self.tab._start_download()

        text = self.tab.logbox.text.get("1.0", "end")
        self.assertIn("⛔ Sécurité", text)
        self.assertIn("File terminée : 1", text)

    def test_cancelling_stops_the_whole_queue(self):
        from core.video_downloader import CancelledError

        for url in ("https://example.com/a", "https://example.com/b"):
            self.tab.url_entry.delete(0, "end")
            self.tab.url_entry.insert(0, url)
            self.tab._enqueue()

        seen = []

        def fake_download(url, dest, *a, **kw):
            seen.append(url)
            raise CancelledError("annulé")

        with patch.object(self.tab.downloader, "download", side_effect=fake_download):
            self.tab._start_download()

        self.assertEqual(len(seen), 1)   # la file s'arrête net
        self.assertIn("annulé", self.tab.logbox.text.get("1.0", "end"))

    def test_start_download_cancelled_logged(self):
        from core.video_downloader import CancelledError

        self.tab.url_entry.insert(0, "https://example.com/watch")
        with patch.object(self.tab.downloader, "download", side_effect=CancelledError("annulé")):
            self.tab._start_download()
        self.assertIn("annulé", self.tab.logbox.text.get("1.0", "end"))

    def test_start_download_security_error_logged(self):
        self.tab.url_entry.insert(0, "https://example.com/watch")
        with patch.object(self.tab.downloader, "download", side_effect=SecurityError("chemin invalide")):
            self.tab._start_download()
        self.assertIn("Sécurité", self.tab.logbox.text.get("1.0", "end"))

    def test_start_download_generic_error_logged(self):
        self.tab.url_entry.insert(0, "https://example.com/watch")
        with patch.object(self.tab.downloader, "download", side_effect=RuntimeError("panne réseau")):
            self.tab._start_download()
        self.assertIn("Erreur :", self.tab.logbox.text.get("1.0", "end"))


class TestConverterTab(_TkTestCase):
    def setUp(self):
        super().setUp()
        from ui.tab_converter import ConverterTab

        self.app = SimpleNamespace(config_data={"output_dir": tempfile.gettempdir()})
        self.tab = ConverterTab(self.root, self.app)
        _sync_after(self.tab)
        _sync_after(self.tab.logbox)

    def tearDown(self):
        self.tab.destroy()
        super().tearDown()

    def test_add_files_mixes_duplicate_unsupported_and_valid(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            valid = Path(tmp_dir) / "photo.png"
            valid.write_bytes(b"\x89PNG\r\n\x1a\n")
            unsupported = Path(tmp_dir) / "data.xyz"
            unsupported.write_text("x")

            with patch("ui.tab_converter.filedialog.askopenfilenames",
                       return_value=(str(valid), str(unsupported))):
                self.tab._add_files()
                # Deuxième appel : le fichier valide est déjà présent (branche "continue").
                self.tab._add_files()

        self.assertEqual(self.tab.files.count(str(valid)), 1)
        self.assertIn("non supporté", self.tab.logbox.text.get("1.0", "end"))
        self.assertNotEqual(self.tab.target_menu.cget("values"), ["—"])

    def test_clear_resets_list_and_target_menu(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            valid = Path(tmp_dir) / "photo.png"
            valid.write_bytes(b"\x89PNG\r\n\x1a\n")
            with patch("ui.tab_converter.filedialog.askopenfilenames", return_value=(str(valid),)):
                self.tab._add_files()
        self.tab._clear()
        self.assertEqual(self.tab.files, [])
        self.assertEqual(self.tab.target_menu.get(), "—")

    def test_browse_updates_destination(self):
        with patch("ui.tab_converter.filedialog.askdirectory", return_value="D:/sortie"):
            self.tab._browse()
        self.assertEqual(self.tab.dest_entry.get(), "D:/sortie")

    def test_convert_all_no_files_logs_error(self):
        self.tab._convert_all()
        self.assertIn("Aucun fichier", self.tab.logbox.text.get("1.0", "end"))

    def test_convert_all_no_target_logs_error(self):
        self.tab.files = ["fake.png"]
        self.tab._convert_all()
        self.assertIn("format cible", self.tab.logbox.text.get("1.0", "end"))

    def test_convert_all_success_security_and_generic_errors(self):
        self.tab.files = ["a.png", "b.png", "c.png"]
        self.tab.target_menu.configure(values=["PNG"])
        self.tab.target_menu.set("PNG")

        def fake_convert(src, target, dest, cb=None, max_width=0, quality=0,
                         max_height=0, crf=0):
            if src == "a.png":
                return "out/a.png"
            if src == "b.png":
                raise SecurityError("fichier trop volumineux")
            raise RuntimeError("format cassé")

        with patch("ui.tab_converter.convert_file", side_effect=fake_convert):
            self.tab._convert_all()

        text = self.tab.logbox.text.get("1.0", "end")
        self.assertIn("✔", text)
        self.assertIn("refusé (sécurité)", text)
        self.assertIn("✖", text)
        self.assertIn("Conversion terminée", text)
        self.assertEqual(self.tab.convert_btn.cget("state"), "normal")

    def test_image_options_are_passed_to_the_converter(self):
        from ui.tab_converter import IMAGE_QUALITIES, IMAGE_WIDTHS

        self.tab.files = ["photo.png"]
        self.tab.target_menu.configure(values=["JPG"])
        self.tab.target_menu.set("JPG")
        self.tab.width_menu.set("800 px (web)")
        self.tab.quality_menu.set("Moyenne (70)")

        captured = {}

        def fake_convert(src, target, dest, cb=None, max_width=0, quality=0,
                         max_height=0, crf=0):
            captured.update(max_width=max_width, quality=quality)
            return "out/photo.jpg"

        with patch("ui.tab_converter.convert_file", side_effect=fake_convert):
            self.tab._convert_all()

        self.assertEqual(captured["max_width"], IMAGE_WIDTHS["800 px (web)"])
        self.assertEqual(captured["quality"], IMAGE_QUALITIES["Moyenne (70)"])

    def test_default_image_options_mean_no_change(self):
        self.tab.files = ["photo.png"]
        self.tab.target_menu.configure(values=["PNG"])
        self.tab.target_menu.set("PNG")
        captured = {}

        def fake_convert(src, target, dest, cb=None, max_width=0, quality=0,
                         max_height=0, crf=0):
            captured.update(max_width=max_width, quality=quality)
            return "out/photo.png"

        with patch("ui.tab_converter.convert_file", side_effect=fake_convert):
            self.tab._convert_all()

        self.assertEqual(captured["max_width"], 0)
        self.assertEqual(captured["quality"], 0)


class TestPdfTab(_TkTestCase):
    def setUp(self):
        super().setUp()
        from ui.tab_pdf import PdfTab

        self.app = SimpleNamespace(config_data={"output_dir": tempfile.gettempdir()})
        self.tab = PdfTab(self.root, self.app)
        _sync_after(self.tab)
        _sync_after(self.tab.logbox)

    def tearDown(self):
        self.tab.destroy()
        super().tearDown()

    def test_add_pdfs_valid_file_renders_row(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "a.pdf"
            _build_pdf(pdf_path)
            with patch("ui.tab_pdf.filedialog.askopenfilenames", return_value=(str(pdf_path),)):
                self.tab._add_pdfs()
        self.assertEqual(len(self.tab.items), 1)
        self.assertTrue(self.tab.list_frame.winfo_children())

    def test_add_pdfs_security_error_logged(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pdf_path = Path(tmp_dir) / "a.pdf"
            _build_pdf(pdf_path)
            with patch("core.pdf_merger.check_file_size", side_effect=SecurityError("trop volumineux")), \
                 patch("ui.tab_pdf.filedialog.askopenfilenames", return_value=(str(pdf_path),)):
                self.tab._add_pdfs()
        self.assertEqual(len(self.tab.items), 0)
        self.assertIn("refusé (sécurité)", self.tab.logbox.text.get("1.0", "end"))

    def test_add_pdfs_invalid_pdf_logged(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad = Path(tmp_dir) / "bad.pdf"
            bad.write_bytes(b"not a real pdf")
            with patch("ui.tab_pdf.filedialog.askopenfilenames", return_value=(str(bad),)):
                self.tab._add_pdfs()
        self.assertEqual(len(self.tab.items), 0)
        self.assertIn("PDF invalide", self.tab.logbox.text.get("1.0", "end"))

    def test_move_and_remove(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            p1, p2 = Path(tmp_dir) / "a.pdf", Path(tmp_dir) / "b.pdf"
            _build_pdf(p1, "A")
            _build_pdf(p2, "B")
            with patch("ui.tab_pdf.filedialog.askopenfilenames", return_value=(str(p1), str(p2))):
                self.tab._add_pdfs()

            first_path = self.tab.items[0].path
            self.tab._move(0, 1)
            self.assertEqual(self.tab.items[1].path, first_path)

            # Hors bornes : ne doit rien changer ni lever.
            self.tab._move(0, -1)

            self.tab._remove(0)
            self.assertEqual(len(self.tab.items), 1)

    def test_browse_out_updates_entry(self):
        with patch("ui.tab_pdf.filedialog.asksaveasfilename", return_value="D:/sortie/fusion.pdf"):
            self.tab._browse_out()
        self.assertEqual(self.tab.out_entry.get(), "D:/sortie/fusion.pdf")

    def test_browse_out_cancelled_keeps_entry(self):
        before = self.tab.out_entry.get()
        with patch("ui.tab_pdf.filedialog.asksaveasfilename", return_value=""):
            self.tab._browse_out()
        self.assertEqual(self.tab.out_entry.get(), before)

    def test_merge_no_items_logs_error(self):
        self.tab._merge()
        self.assertIn("Ajoutez au moins un PDF", self.tab.logbox.text.get("1.0", "end"))

    def test_merge_success_enables_open_button(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            from core.pdf_merger import PdfItem

            pdf_path = Path(tmp_dir) / "a.pdf"
            _build_pdf(pdf_path)
            self.tab.items = [PdfItem(str(pdf_path))]
            self.tab.out_entry.delete(0, "end")
            self.tab.out_entry.insert(0, str(Path(tmp_dir) / "out.pdf"))
            self.tab._merge()
        self.assertEqual(self.tab.open_btn.cget("state"), "normal")
        self.assertIn("PDF généré", self.tab.logbox.text.get("1.0", "end"))

    def test_merge_security_error_logged(self):
        from core.pdf_merger import PdfItem

        self.tab.items = [PdfItem("fake.pdf")]
        with patch("ui.tab_pdf.merge_pdfs", side_effect=SecurityError("trop gros")):
            self.tab._merge()
        self.assertIn("⛔ Sécurité", self.tab.logbox.text.get("1.0", "end"))

    def test_merge_generic_error_logged(self):
        from core.pdf_merger import PdfItem

        self.tab.items = [PdfItem("fake.pdf")]
        with patch("ui.tab_pdf.merge_pdfs", side_effect=RuntimeError("échec")):
            self.tab._merge()
        self.assertIn("Erreur de fusion", self.tab.logbox.text.get("1.0", "end"))

    def test_open_result_calls_open_in_explorer(self):
        self.tab.last_output = "C:/sortie/fusion.pdf"
        with patch("ui.tab_pdf.open_in_explorer") as mock_open:
            self.tab._open_result()
        mock_open.assert_called_once_with("C:/sortie/fusion.pdf")

    def test_open_result_noop_without_output(self):
        self.tab.last_output = None
        with patch("ui.tab_pdf.open_in_explorer") as mock_open:
            self.tab._open_result()
        mock_open.assert_not_called()


class TestMultiToolApp(_TkTestCase):
    def _make_app(self):
        from ui.app import MultiToolApp

        with patch("ui.app.load_config", return_value={
                       "theme": "dark", "language": "fr", "output_dir": tempfile.gettempdir()}), \
             patch("ui.app.save_config"):
            app = MultiToolApp()
        return app

    def test_app_builds_tabs(self):
        app = self._make_app()
        try:
            self.assertIn(f"v", app.title())
        finally:
            app.destroy()

    def test_app_icon_branch_swallows_missing_icon_exception(self):
        import os as os_module

        real_isfile = os_module.path.isfile

        def fake_isfile(path):
            # Ne truque que la vérification de l'icône : les autres appels
            # (dont ceux internes de Tk/Tcl à la construction) restent réels.
            if "icon.ico" in str(path):
                return True
            return real_isfile(path)

        with patch("ui.app.load_config", return_value={
                       "theme": "dark", "language": "fr", "output_dir": tempfile.gettempdir()}), \
             patch("ui.app.save_config"), \
             patch("ui.app.os.path.isfile", side_effect=fake_isfile):
            from ui.app import MultiToolApp
            app = MultiToolApp()  # iconbitmap va échouer silencieusement (fichier factice)
        app.destroy()

    def test_open_settings_changes_theme_language_and_output_dir(self):
        app = self._make_app()
        try:
            with patch("ui.app.save_config") as mock_save:
                app._open_settings()
                win = [w for w in app.winfo_children() if isinstance(w, ctk.CTkToplevel)][0]

                menus = _find_all(win, ctk.CTkOptionMenu)
                theme_menu, lang_menu = menus[0], menus[1]
                theme_menu._command("light")
                self.assertEqual(app.config_data["theme"], "light")

                lang_menu._command("en")
                self.assertEqual(app.config_data["language"], "en")

                browse_btn = _find_by_text(win, ctk.CTkButton, "Parcourir...")[0]
                with patch("ui.app.filedialog.askdirectory", return_value="D:/sortie"):
                    browse_btn._command()
                self.assertEqual(app.config_data["output_dir"], "D:/sortie")

                with patch("ui.app.filedialog.askdirectory", return_value=""):
                    browse_btn._command()  # annulé : ne doit pas lever ni changer la valeur
                self.assertEqual(app.config_data["output_dir"], "D:/sortie")

                self.assertGreaterEqual(mock_save.call_count, 3)
                win.destroy()
        finally:
            app.destroy()

    def test_yt_dlp_update_button_reports_success(self):
        app = self._make_app()
        _sync_after(app)
        try:
            app._open_settings()
            with patch("ui.app.update_yt_dlp", return_value=(True, "yt-dlp mis à jour")):
                app._update_yt_dlp()
            self.assertIn("mis à jour", app.update_label.cget("text"))
            self.assertEqual(app.update_btn.cget("state"), "normal")
        finally:
            app.destroy()

    def test_yt_dlp_update_button_reports_failure(self):
        app = self._make_app()
        _sync_after(app)
        try:
            app._open_settings()
            with patch("ui.app.update_yt_dlp", return_value=(False, "Échec : pas de réseau")):
                app._update_yt_dlp()
            self.assertIn("Échec", app.update_label.cget("text"))
        finally:
            app.destroy()

    def test_app_update_button_announces_a_newer_version(self):
        app = self._make_app()
        _sync_after(app)
        try:
            app._open_settings()
            with patch("ui.app.check_app_update",
                       return_value=(True, "Version 2.0.0 disponible")):
                app._check_app_update()
            self.assertIn("2.0.0", app.app_update_label.cget("text"))
            self.assertEqual(app.app_update_btn.cget("state"), "normal")
        finally:
            app.destroy()

    def test_app_update_button_reports_being_up_to_date(self):
        app = self._make_app()
        _sync_after(app)
        try:
            app._open_settings()
            with patch("ui.app.check_app_update",
                       return_value=(False, "Vous utilisez la dernière version")):
                app._check_app_update()
            self.assertIn("dernière version", app.app_update_label.cget("text"))
        finally:
            app.destroy()

    def test_app_update_result_ignored_when_window_was_closed(self):
        app = self._make_app()
        try:
            app._open_settings()
            for child in app.winfo_children():
                if isinstance(child, ctk.CTkToplevel):
                    child.destroy()
            app._show_app_update_result(True, "terminé")  # ne doit pas lever
        finally:
            app.destroy()

    def test_settings_are_remembered_between_sessions(self):
        # La mémoire passe par le fichier de configuration : on vérifie que la
        # valeur y est bien écrite, et sous sa clé française.
        app = self._make_app()
        try:
            with patch("ui.app.save_config") as mock_save:
                app.remember("conv.largeur", "800 px (web)")
            self.assertEqual(app.recall("conv.largeur"), "800 px (web)")
            self.assertEqual(app.recall("inconnu", "defaut"), "defaut")
            mock_save.assert_called_once()
        finally:
            app.destroy()

    def test_update_result_ignored_when_settings_window_was_closed(self):
        # La mise à jour tourne en tâche de fond : l'utilisateur peut refermer
        # la fenêtre avant la fin, et le résultat n'a alors plus où s'afficher.
        app = self._make_app()
        try:
            app._open_settings()
            for child in app.winfo_children():
                if isinstance(child, ctk.CTkToplevel):
                    child.destroy()
            app._show_update_result(True, "terminé")  # ne doit pas lever
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
