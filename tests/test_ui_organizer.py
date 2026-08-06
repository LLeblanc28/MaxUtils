"""Tests de l'onglet Organiser (réordonner, supprimer, pivoter les pages).

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
        self._target, self._args, self._kwargs = target, args, kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)


def _sync_after(widget) -> None:
    widget.after = lambda ms, fn=None, *a, **kw: (fn(*a, **kw) if fn else None)


def _build_pdf(path: Path, pages: int = 4) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    for i in range(pages):
        c.drawString(72, 700, f"PAGE {i + 1}")
        c.showPage()
    c.save()


class _OrganizerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        from ui.tab_pdf_organizer import PdfOrganizerTab

        self.thread_patcher = patch("threading.Thread", _SyncThread)
        self.thread_patcher.start()
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.app = SimpleNamespace(config_data={"output_dir": str(self.tmp_path)})
        self.tab = PdfOrganizerTab(self.root, self.app)
        _sync_after(self.tab)
        _sync_after(self.tab.logbox)

    def tearDown(self):
        self.tab.destroy()
        self.tmp.cleanup()
        self.thread_patcher.stop()

    def _log(self) -> str:
        return self.tab.logbox.text.get("1.0", "end")

    def _load(self, pages: int = 4) -> Path:
        src = self.tmp_path / "doc.pdf"
        _build_pdf(src, pages=pages)
        with patch("ui.tab_pdf_organizer.filedialog.askopenfilename", return_value=str(src)):
            self.tab._pick_source()
        return src


class TestLoading(_OrganizerTestCase):
    def test_loading_builds_one_tile_per_page(self):
        self._load(pages=4)
        self.assertEqual(len(self.tab.pages), 4)
        self.assertEqual(len(self.tab._thumbnails), 4)
        self.assertTrue(self.tab.grid_frame.winfo_children())
        self.assertIn("4 pages", self.tab.source_label.cget("text"))

    def test_cancelling_the_dialog_loads_nothing(self):
        with patch("ui.tab_pdf_organizer.filedialog.askopenfilename", return_value=""):
            self.tab._pick_source()
        self.assertIsNone(self.tab.source)

    def test_dropping_a_pdf_loads_it(self):
        src = self.tmp_path / "doc.pdf"
        _build_pdf(src, pages=2)
        self.tab._on_drop([str(src)])
        self.assertEqual(len(self.tab.pages), 2)

    def test_dropping_several_keeps_only_the_first(self):
        first, second = self.tmp_path / "a.pdf", self.tmp_path / "b.pdf"
        _build_pdf(first, pages=3)
        _build_pdf(second, pages=1)
        self.tab._on_drop([str(first), str(second)])
        self.assertEqual(len(self.tab.pages), 3)
        self.assertIn("Un seul PDF", self._log())

    def test_empty_drop_is_ignored(self):
        self.tab._on_drop([])
        self.assertIsNone(self.tab.source)

    def test_protected_pdf_is_reported(self):
        src = self.tmp_path / "clair.pdf"
        _build_pdf(src, pages=1)
        locked = protect_pdf(str(src), str(self.tmp_path / "verrouille.pdf"), "abc")
        with patch("ui.tab_pdf_organizer.filedialog.askopenfilename", return_value=locked):
            self.tab._pick_source()
        self.assertIsNone(self.tab.source)
        self.assertIn("🔒", self._log())

    def test_oversized_pdf_is_refused(self):
        src = self.tmp_path / "doc.pdf"
        _build_pdf(src, pages=1)
        with patch("ui.tab_pdf_organizer.page_count",
                   side_effect=SecurityError("trop gros")), \
             patch("ui.tab_pdf_organizer.filedialog.askopenfilename", return_value=str(src)):
            self.tab._pick_source()
        self.assertIn("refusé (sécurité)", self._log())

    def test_unreadable_pdf_is_reported(self):
        broken = self.tmp_path / "casse.pdf"
        broken.write_bytes(b"pas un pdf")
        with patch("ui.tab_pdf_organizer.filedialog.askopenfilename", return_value=str(broken)):
            self.tab._pick_source()
        self.assertIn("illisible", self._log())

    def test_render_without_a_document_does_nothing(self):
        self.tab._render()
        self.assertEqual(self.tab.grid_frame.winfo_children(), [])


class TestEditing(_OrganizerTestCase):
    def test_actions_require_a_selection(self):
        self._load()
        for action in (lambda: self.tab._move(1), lambda: self.tab._rotate(90),
                       self.tab._delete):
            action()
        self.assertIn("Sélectionnez d'abord une page", self._log())

    def test_selecting_highlights_a_tile(self):
        self._load()
        self.tab._select(2)
        self.assertEqual(self.tab.selected, 2)

    def test_moving_a_page_forward_and_back(self):
        self._load(pages=3)
        self.tab._select(0)
        self.tab._move(1)
        self.assertEqual(self.tab.pages[1][0], 0)
        self.assertEqual(self.tab.selected, 1)

        self.tab._move(-1)
        self.assertEqual(self.tab.pages[0][0], 0)

    def test_moving_beyond_the_edges_does_nothing(self):
        self._load(pages=2)
        self.tab._select(0)
        self.tab._move(-1)
        self.assertEqual(self.tab.selected, 0)
        self.tab._select(1)
        self.tab._move(1)
        self.assertEqual(self.tab.selected, 1)

    def test_rotation_accumulates_and_wraps(self):
        self._load()
        self.tab._select(0)
        self.tab._rotate(90)
        self.tab._rotate(90)
        self.assertEqual(self.tab.pages[0][1], 180)
        self.tab._rotate(-90)
        self.assertEqual(self.tab.pages[0][1], 90)

    def test_deleting_removes_the_page_and_clears_the_selection(self):
        self._load(pages=3)
        self.tab._select(1)
        self.tab._delete()
        self.assertEqual(len(self.tab.pages), 2)
        self.assertIsNone(self.tab.selected)

    def test_the_last_page_cannot_be_deleted(self):
        self._load(pages=1)
        self.tab._select(0)
        self.tab._delete()
        self.assertEqual(len(self.tab.pages), 1)
        self.assertIn("au moins une page", self._log())

    def test_reset_restores_the_original_order(self):
        self._load(pages=3)
        self.tab._select(0)
        self.tab._delete()
        self.tab._reset()
        self.assertEqual(len(self.tab.pages), 3)
        self.assertEqual([p[0] for p in self.tab.pages], [0, 1, 2])

    def test_reset_without_a_document_warns(self):
        self.tab._reset()
        self.assertIn("Choisissez d'abord un PDF", self._log())


class TestSaving(_OrganizerTestCase):
    def test_saving_without_a_document_warns(self):
        self.tab._save()
        self.assertIn("Choisissez d'abord un PDF", self._log())

    def test_cancelling_the_save_dialog(self):
        self._load()
        with patch("ui.tab_pdf_organizer.filedialog.asksaveasfilename", return_value=""):
            self.tab._save()
        self.assertNotIn("réorganisé", self._log())

    def test_saving_applies_order_deletion_and_rotation(self):
        import fitz

        self._load(pages=4)
        self.tab._select(0)
        self.tab._move(1)          # page 1 passe en 2e position
        self.tab._select(3)
        self.tab._rotate(90)       # dernière page pivotée
        self.tab._select(0)
        self.tab._delete()         # retire ce qui est désormais en tête

        target = self.tmp_path / "out.pdf"
        with patch("ui.tab_pdf_organizer.filedialog.asksaveasfilename",
                   return_value=str(target)):
            self.tab._save()

        self.assertIn("réorganisé", self._log())
        self.assertEqual(page_count(str(target)), 3)
        doc = fitz.open(str(target))
        try:
            self.assertIn("PAGE 1", doc[0].get_text())
            self.assertIn("PAGE 3", doc[1].get_text())
            self.assertEqual(doc[2].rotation, 90)
        finally:
            doc.close()

    def test_security_error_is_logged(self):
        self._load()
        with patch("ui.tab_pdf_organizer.filedialog.asksaveasfilename",
                   return_value=str(self.tmp_path / "x.pdf")), \
             patch("ui.tab_pdf_organizer.organize_pages",
                   side_effect=SecurityError("trop gros")):
            self.tab._save()
        self.assertIn("⛔ Sécurité", self._log())

    def test_value_error_is_logged(self):
        self._load()
        with patch("ui.tab_pdf_organizer.filedialog.asksaveasfilename",
                   return_value=str(self.tmp_path / "x.pdf")), \
             patch("ui.tab_pdf_organizer.organize_pages",
                   side_effect=ValueError("page inexistante")):
            self.tab._save()
        self.assertIn("✖", self._log())

    def test_unexpected_error_is_logged(self):
        self._load()
        with patch("ui.tab_pdf_organizer.filedialog.asksaveasfilename",
                   return_value=str(self.tmp_path / "x.pdf")), \
             patch("ui.tab_pdf_organizer.organize_pages",
                   side_effect=RuntimeError("disque plein")):
            self.tab._save()
        self.assertIn("Erreur :", self._log())


if __name__ == "__main__":
    unittest.main()
