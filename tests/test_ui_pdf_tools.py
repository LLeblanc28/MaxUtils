"""Tests de l'onglet Outils PDF (découpe, compression, protection).

Mêmes conventions que les autres tests d'interface : widgets réels sans
mainloop, threads rendus synchrones, dialogues systématiquement mockés.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk

from core.pdf_tools import page_count, protect_pdf
from utils.security import SecurityError


class _SyncThread:
    def __init__(self, target=None, daemon=None, args=(), kwargs=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)


def _sync_after(widget) -> None:
    widget.after = lambda ms, fn=None, *a, **kw: (fn(*a, **kw) if fn else None)


def _build_pdf(path: Path, pages: int = 5) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    for i in range(pages):
        c.drawString(72, 780, f"PAGE NUMERO {i + 1}")
        c.showPage()
    c.save()


class _ToolsTabTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        from ui.tab_pdf_tools import PdfToolsTab

        self.thread_patcher = patch("threading.Thread", _SyncThread)
        self.thread_patcher.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.app = SimpleNamespace(config_data={"output_dir": str(self.tmp_path)})
        self.tab = PdfToolsTab(self.root, self.app)
        _sync_after(self.tab)
        _sync_after(self.tab.logbox)

    def tearDown(self):
        self.tab.destroy()
        self.tmp.cleanup()
        self.thread_patcher.stop()

    def _log(self) -> str:
        return self.tab.logbox.text.get("1.0", "end")

    def _load(self, pages: int = 5) -> Path:
        src = self.tmp_path / "doc.pdf"
        _build_pdf(src, pages=pages)
        with patch("ui.tab_pdf_tools.filedialog.askopenfilename", return_value=str(src)):
            self.tab._pick_source()
        return src


class TestSourceSelection(_ToolsTabTestCase):
    def test_selecting_a_pdf_shows_its_page_count(self):
        self._load(pages=7)
        self.assertIn("7 page(s)", self.tab.source_label.cget("text"))
        self.assertIn("Chargé", self._log())

    def test_cancelling_the_dialog_keeps_no_source(self):
        with patch("ui.tab_pdf_tools.filedialog.askopenfilename", return_value=""):
            self.tab._pick_source()
        self.assertIsNone(self.tab.source)

    def test_protected_pdf_is_kept_but_reported(self):
        src = self.tmp_path / "clair.pdf"
        _build_pdf(src, pages=2)
        locked = protect_pdf(str(src), str(self.tmp_path / "verrouille.pdf"), "abc")
        with patch("ui.tab_pdf_tools.filedialog.askopenfilename", return_value=locked):
            self.tab._pick_source()
        # Le fichier reste sélectionné : l'utilisateur saisit le mot de passe
        # puis relance l'opération sans avoir à re-parcourir ses dossiers.
        self.assertEqual(self.tab.source, locked)
        self.assertIn("🔒", self._log())

    def test_oversized_pdf_is_refused(self):
        src = self.tmp_path / "doc.pdf"
        _build_pdf(src, pages=1)
        with patch("ui.tab_pdf_tools.page_count", side_effect=SecurityError("trop gros")), \
             patch("ui.tab_pdf_tools.filedialog.askopenfilename", return_value=str(src)):
            self.tab._pick_source()
        self.assertIn("refusé (sécurité)", self._log())

    def test_unreadable_pdf_is_reported(self):
        broken = self.tmp_path / "casse.pdf"
        broken.write_bytes(b"pas un pdf")
        with patch("ui.tab_pdf_tools.filedialog.askopenfilename", return_value=str(broken)):
            self.tab._pick_source()
        self.assertIn("illisible", self._log())


class TestSplitAction(_ToolsTabTestCase):
    def test_split_without_source_warns(self):
        self.tab._split()
        self.assertIn("Choisissez d'abord un PDF", self._log())

    def test_split_cancelled_at_folder_dialog(self):
        self._load()
        with patch("ui.tab_pdf_tools.filedialog.askdirectory", return_value=""):
            self.tab._split()
        self.assertNotIn("créé", self._log())

    def test_split_extracts_a_single_file(self):
        self._load(pages=5)
        self.tab.split_range.insert(0, "2-3")
        out_dir = self.tmp_path / "sortie"
        out_dir.mkdir()
        with patch("ui.tab_pdf_tools.filedialog.askdirectory", return_value=str(out_dir)):
            self.tab._split()

        created = list(out_dir.glob("*.pdf"))
        self.assertEqual(len(created), 1)
        self.assertEqual(page_count(str(created[0])), 2)
        self.assertIn("PDF créé", self._log())

    def test_split_per_page_creates_one_file_per_page(self):
        self._load(pages=3)
        self.tab.split_mode.set("per_page")
        out_dir = self.tmp_path / "pages"
        out_dir.mkdir()
        with patch("ui.tab_pdf_tools.filedialog.askdirectory", return_value=str(out_dir)):
            self.tab._split()

        self.assertEqual(len(list(out_dir.glob("*.pdf"))), 3)
        self.assertIn("3 fichier(s)", self._log())

    def test_invalid_range_is_reported_without_crashing(self):
        self._load(pages=3)
        self.tab.split_range.insert(0, "1-99")
        with patch("ui.tab_pdf_tools.filedialog.askdirectory", return_value=str(self.tmp_path)):
            self.tab._split()
        self.assertIn("✖", self._log())


class TestCompressAction(_ToolsTabTestCase):
    def test_compress_without_source_warns(self):
        self.tab._compress()
        self.assertIn("Choisissez d'abord un PDF", self._log())

    def test_compress_cancelled_at_save_dialog(self):
        self._load()
        with patch("ui.tab_pdf_tools.filedialog.asksaveasfilename", return_value=""):
            self.tab._compress()
        self.assertEqual(self.tab.compress_result.cget("text"), "")

    def test_compress_reports_the_size_change(self):
        self._load(pages=6)
        target = self.tmp_path / "compresse.pdf"
        with patch("ui.tab_pdf_tools.filedialog.asksaveasfilename", return_value=str(target)):
            self.tab._compress()

        self.assertTrue(target.exists())
        self.assertEqual(page_count(str(target)), 6)
        self.assertIn("→", self.tab.compress_result.cget("text"))

    def test_ratio_wording_for_gain_and_for_no_gain(self):
        self.assertIn("−50 %", self.tab._ratio(2000, 1000))
        self.assertIn("aucun gain", self.tab._ratio(1000, 1200))
        self.assertIn("aucun gain", self.tab._ratio(1000, 1000))

    def test_security_error_during_compression_is_logged(self):
        self._load()
        with patch("ui.tab_pdf_tools.filedialog.asksaveasfilename",
                   return_value=str(self.tmp_path / "x.pdf")), \
             patch("ui.tab_pdf_tools.compress_pdf", side_effect=SecurityError("trop gros")):
            self.tab._compress()
        self.assertIn("⛔ Sécurité", self._log())

    def test_unexpected_error_during_compression_is_logged(self):
        self._load()
        with patch("ui.tab_pdf_tools.filedialog.asksaveasfilename",
                   return_value=str(self.tmp_path / "x.pdf")), \
             patch("ui.tab_pdf_tools.compress_pdf", side_effect=RuntimeError("disque plein")):
            self.tab._compress()
        self.assertIn("Erreur :", self._log())


class TestProtectAndUnlockActions(_ToolsTabTestCase):
    def test_protect_without_source_warns(self):
        self.tab._protect()
        self.assertIn("Choisissez d'abord un PDF", self._log())

    def test_protect_without_password_warns(self):
        self._load()
        self.tab._protect()
        self.assertIn("Saisissez le nouveau mot de passe", self._log())

    def test_protect_cancelled_at_save_dialog(self):
        self._load()
        self.tab.new_password.insert(0, "secret")
        with patch("ui.tab_pdf_tools.filedialog.asksaveasfilename", return_value=""):
            self.tab._protect()
        self.assertNotIn("protégé", self._log())

    def test_protect_produces_a_locked_file(self):
        self._load(pages=2)
        self.tab.new_password.insert(0, "MonSecret")
        target = self.tmp_path / "protege.pdf"
        with patch("ui.tab_pdf_tools.filedialog.asksaveasfilename", return_value=str(target)):
            self.tab._protect()

        self.assertIn("AES-256", self._log())
        with self.assertRaises(ValueError):
            page_count(str(target))
        self.assertEqual(page_count(str(target), password="MonSecret"), 2)

    def test_protect_without_printing_permission(self):
        self._load(pages=1)
        self.tab.new_password.insert(0, "pw")
        self.tab.allow_printing.set(False)
        target = self.tmp_path / "sansimpression.pdf"
        with patch("ui.tab_pdf_tools.filedialog.asksaveasfilename", return_value=str(target)):
            self.tab._protect()
        self.assertTrue(target.exists())

    def test_unlock_without_source_warns(self):
        self.tab._unlock()
        self.assertIn("Choisissez d'abord un PDF", self._log())

    def test_unlock_without_password_warns(self):
        self._load()
        self.tab._unlock()
        self.assertIn("Saisissez le mot de passe du fichier", self._log())

    def test_unlock_cancelled_at_save_dialog(self):
        self._load()
        self.tab.source_password.insert(0, "abc")
        with patch("ui.tab_pdf_tools.filedialog.asksaveasfilename", return_value=""):
            self.tab._unlock()
        self.assertNotIn("déverrouillé", self._log())

    def test_unlock_removes_the_password(self):
        src = self.tmp_path / "clair.pdf"
        _build_pdf(src, pages=3)
        locked = protect_pdf(str(src), str(self.tmp_path / "verrouille.pdf"), "abc")

        with patch("ui.tab_pdf_tools.filedialog.askopenfilename", return_value=locked):
            self.tab._pick_source()
        self.tab.source_password.insert(0, "abc")
        target = self.tmp_path / "ouvert.pdf"
        with patch("ui.tab_pdf_tools.filedialog.asksaveasfilename", return_value=str(target)):
            self.tab._unlock()

        self.assertIn("déverrouillé", self._log())
        self.assertEqual(page_count(str(target)), 3)

    def test_unlock_with_wrong_password_is_reported(self):
        src = self.tmp_path / "clair.pdf"
        _build_pdf(src, pages=1)
        locked = protect_pdf(str(src), str(self.tmp_path / "verrouille.pdf"), "abc")

        with patch("ui.tab_pdf_tools.filedialog.askopenfilename", return_value=locked):
            self.tab._pick_source()
        self.tab.source_password.insert(0, "mauvais")
        with patch("ui.tab_pdf_tools.filedialog.asksaveasfilename",
                   return_value=str(self.tmp_path / "o.pdf")):
            self.tab._unlock()
        self.assertIn("incorrect", self._log())


if __name__ == "__main__":
    unittest.main()
