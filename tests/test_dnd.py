"""Tests du glisser-déposer (ui/dnd.py) et de son branchement dans les onglets.

tkinterdnd2 s'appuie sur des binaires natifs : les tests couvrent aussi bien
le cas où la bibliothèque est présente que celui où elle manque, puisque
l'application doit rester pleinement utilisable dans les deux situations.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk

from ui.dnd import enable_dnd, parse_drop_paths, register_drop_target


class _SyncThread:
    def __init__(self, target=None, daemon=None, args=(), kwargs=None):
        self._target, self._args, self._kwargs = target, args, kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)


def _sync_after(widget) -> None:
    widget.after = lambda ms, fn=None, *a, **kw: (fn(*a, **kw) if fn else None)


def _build_pdf(path: Path, pages: int = 2) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    for i in range(pages):
        c.drawString(72, 780, f"Page {i + 1}")
        c.showPage()
    c.save()


class TestEnableDnd(unittest.TestCase):
    def test_returns_false_when_library_is_missing(self):
        with patch.dict(sys.modules, {"tkinterdnd2": None}):
            self.assertFalse(enable_dnd(MagicMock()))

    def test_returns_false_when_native_library_fails_to_load(self):
        fake = MagicMock()
        fake.TkinterDnD.require.side_effect = RuntimeError("tkdnd introuvable")
        with patch.dict(sys.modules, {"tkinterdnd2": fake}):
            self.assertFalse(enable_dnd(MagicMock()))

    def test_returns_true_and_records_the_version(self):
        fake = MagicMock()
        fake.TkinterDnD.require.return_value = "2.9"
        root = MagicMock()
        with patch.dict(sys.modules, {"tkinterdnd2": fake}):
            self.assertTrue(enable_dnd(root))
        self.assertEqual(root.TkdndVersion, "2.9")


class TestParseDropPaths(unittest.TestCase):
    """Le format renvoyé par tkdnd est une liste Tcl, pas une chaîne séparée
    par des espaces : les chemins contenant des espaces sont entre accolades."""

    @classmethod
    def setUpClass(cls):
        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_single_path(self):
        self.assertEqual(parse_drop_paths(self.root, "C:/dossier/a.pdf"),
                         ["C:/dossier/a.pdf"])

    def test_several_paths(self):
        result = parse_drop_paths(self.root, "C:/a.pdf C:/b.pdf")
        self.assertEqual(result, ["C:/a.pdf", "C:/b.pdf"])

    def test_path_containing_spaces_stays_whole(self):
        result = parse_drop_paths(self.root, "{C:/mes documents/rapport final.pdf}")
        self.assertEqual(result, ["C:/mes documents/rapport final.pdf"])

    def test_mixed_quoted_and_plain_paths(self):
        result = parse_drop_paths(self.root, "{C:/mes documents/a.pdf} C:/b.pdf")
        self.assertEqual(result, ["C:/mes documents/a.pdf", "C:/b.pdf"])

    def test_empty_data_gives_no_path(self):
        self.assertEqual(parse_drop_paths(self.root, ""), [])

    def test_unparseable_data_falls_back_to_the_raw_string(self):
        widget = SimpleNamespace(tk=SimpleNamespace(
            splitlist=MagicMock(side_effect=RuntimeError("Tcl error"))))
        self.assertEqual(parse_drop_paths(widget, "C:/a.pdf"), ["C:/a.pdf"])


class TestRegisterDropTarget(unittest.TestCase):
    def test_returns_false_when_library_is_missing(self):
        with patch.dict(sys.modules, {"tkinterdnd2": None}):
            self.assertFalse(register_drop_target(MagicMock(), lambda paths: None))

    def test_returns_false_when_widget_cannot_be_registered(self):
        widget = MagicMock()
        widget.drop_target_register.side_effect = RuntimeError("non supporté")
        fake = MagicMock(DND_FILES="DND_Files")
        with patch.dict(sys.modules, {"tkinterdnd2": fake}):
            self.assertFalse(register_drop_target(widget, lambda paths: None))

    def test_registers_and_forwards_dropped_paths_to_the_callback(self):
        widget = MagicMock()
        widget.tk.splitlist.return_value = ("C:/a.pdf", "C:/b.pdf")
        received = []
        fake = MagicMock(DND_FILES="DND_Files")

        with patch.dict(sys.modules, {"tkinterdnd2": fake}):
            self.assertTrue(register_drop_target(widget, received.extend))

        widget.drop_target_register.assert_called_once_with("DND_Files")
        # Rejoue le dépôt en appelant le gestionnaire enregistré.
        handler = widget.dnd_bind.call_args[0][1]
        handler(SimpleNamespace(data="C:/a.pdf C:/b.pdf"))
        self.assertEqual(received, ["C:/a.pdf", "C:/b.pdf"])


class TestTabsAcceptDroppedFiles(unittest.TestCase):
    """Les onglets doivent traiter un dépôt exactement comme une sélection
    par le sélecteur de fichiers."""

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
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.app = SimpleNamespace(config_data={"output_dir": str(self.tmp_path)})

    def tearDown(self):
        self.tmp.cleanup()
        self.thread_patcher.stop()

    def test_converter_adds_dropped_files(self):
        from ui.tab_converter import ConverterTab

        tab = ConverterTab(self.root, self.app)
        _sync_after(tab)
        _sync_after(tab.logbox)
        try:
            image = self.tmp_path / "photo.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\n")
            unsupported = self.tmp_path / "inconnu.xyz"
            unsupported.write_text("x")

            tab._add_paths([str(image), str(unsupported)])
            self.assertEqual(tab.files, [str(image)])
            self.assertIn("non supporté", tab.logbox.text.get("1.0", "end"))
        finally:
            tab.destroy()

    def test_merge_tab_adds_dropped_pdfs(self):
        from ui.tab_pdf import PdfTab

        tab = PdfTab(self.root, self.app)
        _sync_after(tab)
        _sync_after(tab.logbox)
        try:
            pdf = self.tmp_path / "doc.pdf"
            _build_pdf(pdf)
            tab._add_paths([str(pdf)])
            self.assertEqual(len(tab.items), 1)
        finally:
            tab.destroy()

    def test_editor_opens_the_first_dropped_pdf_and_says_so(self):
        from ui.tab_pdf_editor import PdfEditorTab

        tab = PdfEditorTab(self.root, self.app)
        _sync_after(tab)
        _sync_after(tab.logbox)
        try:
            first, second = self.tmp_path / "a.pdf", self.tmp_path / "b.pdf"
            _build_pdf(first, pages=3)
            _build_pdf(second, pages=1)

            tab._on_drop([str(first), str(second)])
            self.assertEqual(tab.editor.page_count, 3)
            self.assertIn("Un seul PDF à la fois", tab.logbox.text.get("1.0", "end"))
        finally:
            if tab.editor:
                tab.editor.close()
            tab.destroy()

    def test_editor_ignores_an_empty_drop(self):
        from ui.tab_pdf_editor import PdfEditorTab

        tab = PdfEditorTab(self.root, self.app)
        _sync_after(tab)
        try:
            tab._on_drop([])
            self.assertIsNone(tab.editor)
        finally:
            tab.destroy()

    def test_tools_tab_takes_the_first_dropped_pdf(self):
        from ui.tab_pdf_tools import PdfToolsTab

        tab = PdfToolsTab(self.root, self.app)
        _sync_after(tab)
        _sync_after(tab.logbox)
        try:
            first, second = self.tmp_path / "a.pdf", self.tmp_path / "b.pdf"
            _build_pdf(first, pages=4)
            _build_pdf(second, pages=1)

            tab._on_drop([str(first), str(second)])
            self.assertEqual(tab.source, str(first))
            self.assertIn("4 page(s)", tab.source_label.cget("text"))
        finally:
            tab.destroy()

    def test_tools_tab_ignores_an_empty_drop(self):
        from ui.tab_pdf_tools import PdfToolsTab

        tab = PdfToolsTab(self.root, self.app)
        _sync_after(tab)
        try:
            tab._on_drop([])
            self.assertIsNone(tab.source)
        finally:
            tab.destroy()


if __name__ == "__main__":
    unittest.main()
