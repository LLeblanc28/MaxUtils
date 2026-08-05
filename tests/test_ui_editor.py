"""Tests de l'onglet Éditeur PDF et de la fenêtre de signature.

Mêmes techniques que tests/test_ui.py : vrais widgets customtkinter sans
mainloop, threads rendus synchrones, `after()` immédiat, dialogues toujours
mockés. Les événements souris sont simulés par des objets porteurs de x/y,
ce que les gestionnaires attendent.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customtkinter as ctk

from core.pdf_editor import COLORS, Annotation, Style
from utils.security import SecurityError


class _SyncThread:
    """Remplace threading.Thread : exécute la cible immédiatement."""

    def __init__(self, target=None, daemon=None, args=(), kwargs=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)


def _sync_after(widget) -> None:
    widget.after = lambda ms, fn=None, *a, **kw: (fn(*a, **kw) if fn else None)


def _event(x: float, y: float):
    return SimpleNamespace(x=x, y=y)


def _build_pdf(path: Path, pages: int = 2) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    for i in range(pages):
        c.drawString(72, 780, f"Page {i + 1}")
        c.showPage()
    c.save()


class _TkTestCase(unittest.TestCase):
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


# ===========================================================================
#                            Fenêtre de signature
# ===========================================================================
class TestSignatureDialog(_TkTestCase):
    def _dialog(self):
        from ui.signature_dialog import SignatureDialog

        dlg = SignatureDialog(self.root)
        _sync_after(dlg)
        return dlg

    def test_drawing_strokes_then_validate_produces_png(self):
        dlg = self._dialog()
        dlg._on_press(_event(10, 10))
        dlg._on_drag(_event(40, 30))
        dlg._on_drag(_event(80, 20))
        dlg._on_release(_event(80, 20))
        self.assertEqual(len(dlg._strokes), 1)
        dlg._validate()
        self.assertIsNotNone(dlg.result)
        self.assertTrue(Path(dlg.result).exists())

    def test_validate_without_stroke_shows_error_and_stays_open(self):
        dlg = self._dialog()
        dlg._validate()
        self.assertIsNone(dlg.result)
        self.assertIn("Aucun tracé", dlg.error_label.cget("text"))
        dlg.destroy()

    def test_drag_without_press_is_ignored(self):
        dlg = self._dialog()
        dlg._on_drag(_event(50, 50))
        self.assertEqual(dlg._strokes, [])
        dlg.destroy()

    def test_release_without_press_is_ignored(self):
        dlg = self._dialog()
        dlg._on_release(_event(50, 50))
        self.assertEqual(dlg._strokes, [])
        dlg.destroy()

    def test_clear_resets_canvas_and_strokes(self):
        dlg = self._dialog()
        dlg._on_press(_event(5, 5))
        dlg._on_drag(_event(25, 25))
        dlg._on_release(_event(25, 25))
        dlg._clear()
        self.assertEqual(dlg._strokes, [])
        self.assertEqual(dlg.error_label.cget("text"), "")
        dlg.destroy()

    def test_ink_colour_follows_selection(self):
        dlg = self._dialog()
        dlg.color_menu.set("Rouge")
        r, g, b = COLORS["Rouge"]
        self.assertEqual(dlg._ink(), f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}")
        dlg.destroy()

    def test_import_image_sets_result(self):
        dlg = self._dialog()
        with patch("ui.signature_dialog.filedialog.askopenfilename",
                   return_value="C:/images/signature.png"):
            dlg._import_image()
        self.assertEqual(dlg.result, "C:/images/signature.png")

    def test_import_image_cancelled_keeps_dialog_open(self):
        dlg = self._dialog()
        with patch("ui.signature_dialog.filedialog.askopenfilename", return_value=""):
            dlg._import_image()
        self.assertIsNone(dlg.result)
        dlg.destroy()

    def test_cancel_clears_result(self):
        dlg = self._dialog()
        dlg._on_press(_event(1, 1))
        dlg._on_release(_event(1, 1))
        dlg._cancel()
        self.assertIsNone(dlg.result)


# ===========================================================================
#                             Onglet Éditeur PDF
# ===========================================================================
class _EditorTabTestCase(_TkTestCase):
    def setUp(self):
        super().setUp()
        from ui.tab_pdf_editor import PdfEditorTab

        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.app = SimpleNamespace(config_data={"output_dir": str(self.tmp_path)})
        self.tab = PdfEditorTab(self.root, self.app)
        _sync_after(self.tab)
        _sync_after(self.tab.logbox)

    def tearDown(self):
        if self.tab.editor:
            self.tab.editor.close()
        self.tab.destroy()
        self.tmp.cleanup()
        super().tearDown()

    def _load_pdf(self, pages: int = 2) -> Path:
        src = self.tmp_path / "doc.pdf"
        _build_pdf(src, pages=pages)
        with patch("ui.tab_pdf_editor.filedialog.askopenfilename", return_value=str(src)):
            self.tab._open_pdf()
        return src

    def _log(self) -> str:
        return self.tab.logbox.text.get("1.0", "end")


class TestEditorFileHandling(_EditorTabTestCase):
    def test_open_pdf_loads_document(self):
        self._load_pdf(pages=3)
        self.assertIsNotNone(self.tab.editor)
        self.assertEqual(self.tab.editor.page_count, 3)
        self.assertIn("3 page(s)", self.tab.file_label.cget("text"))
        self.assertIn("Chargé", self._log())

    def test_open_pdf_cancelled_changes_nothing(self):
        with patch("ui.tab_pdf_editor.filedialog.askopenfilename", return_value=""):
            self.tab._open_pdf()
        self.assertIsNone(self.tab.editor)

    def test_open_second_pdf_closes_the_first(self):
        self._load_pdf()
        first = self.tab.editor
        first.close = MagicMock(wraps=first.close)
        other = self.tmp_path / "autre.pdf"
        _build_pdf(other, pages=1)
        with patch("ui.tab_pdf_editor.filedialog.askopenfilename", return_value=str(other)):
            self.tab._open_pdf()
        first.close.assert_called_once()
        self.assertEqual(self.tab.editor.page_count, 1)

    def test_open_pdf_rejected_for_security_is_logged(self):
        src = self.tmp_path / "doc.pdf"
        _build_pdf(src, pages=1)
        with patch("ui.tab_pdf_editor.PdfEditor", side_effect=SecurityError("trop volumineux")), \
             patch("ui.tab_pdf_editor.filedialog.askopenfilename", return_value=str(src)):
            self.tab._open_pdf()
        self.assertIsNone(self.tab.editor)
        self.assertIn("refusé (sécurité)", self._log())

    def test_open_unreadable_pdf_is_logged(self):
        broken = self.tmp_path / "casse.pdf"
        broken.write_bytes(b"pas un vrai pdf")
        with patch("ui.tab_pdf_editor.filedialog.askopenfilename", return_value=str(broken)):
            self.tab._open_pdf()
        self.assertIsNone(self.tab.editor)
        self.assertIn("illisible", self._log())

    def test_opening_a_new_pdf_drops_previous_annotations(self):
        self._load_pdf()
        self.tab.annotations.append(Annotation("text", 0, 10, 10, text="ancien"))
        self._load_pdf()
        self.assertEqual(self.tab.annotations, [])


class TestEditorNavigation(_EditorTabTestCase):
    def test_change_page_without_document_is_ignored(self):
        self.tab._change_page(1)
        self.assertEqual(self.tab.page_index, 0)

    def test_change_page_moves_and_stops_at_bounds(self):
        self._load_pdf(pages=2)
        self.tab._change_page(1)
        self.assertEqual(self.tab.page_index, 1)
        self.assertIn("2 / 2", self.tab.page_label.cget("text"))

        self.tab._change_page(1)   # au-delà de la dernière page
        self.assertEqual(self.tab.page_index, 1)
        self.tab._change_page(-1)
        self.assertEqual(self.tab.page_index, 0)
        self.tab._change_page(-1)  # avant la première page
        self.assertEqual(self.tab.page_index, 0)

    def test_zoom_change_rerenders(self):
        self._load_pdf()
        self.tab._on_zoom_change("150 %")
        self.assertAlmostEqual(self.tab.zoom, 1.5)

    def test_tool_change_is_logged(self):
        self.tab.tool_var.set("arrow")
        self.tab._on_tool_change()
        self.assertIn("Flèche", self._log())

    def test_render_without_document_does_nothing(self):
        self.tab._render()  # ne doit pas lever
        self.assertIsNone(self.tab._photo)


class TestEditorProperties(_EditorTabTestCase):
    def test_percent_parsing(self):
        self.assertAlmostEqual(self.tab._percent("75 %"), 0.75)
        self.assertAlmostEqual(self.tab._percent("100 %"), 1.0)

    def test_hex_conversion(self):
        self.assertEqual(self.tab._hex((0.0, 0.0, 0.0)), "#000000")
        self.assertEqual(self.tab._hex((1.0, 1.0, 1.0)), "#ffffff")

    def test_current_style_reads_the_panel(self):
        self.tab.family_menu.set("Times")
        self.tab.size_menu.set("24")
        self.tab.bold_var.set(True)
        self.tab.italic_var.set(True)
        self.tab.underline_var.set(True)
        self.tab.color_menu.set("Rouge")
        self.tab.fill_menu.set("Jaune")
        self.tab.width_menu.set("5")
        self.tab.opacity_menu.set("50 %")

        style = self.tab._current_style()
        self.assertEqual(style.family, "tiro")
        self.assertEqual(style.size, 24.0)
        self.assertEqual(style.font, "tibi")
        self.assertTrue(style.underline)
        self.assertEqual(style.color, COLORS["Rouge"])
        self.assertEqual(style.fill, COLORS["Jaune"])
        self.assertEqual(style.line_width, 5.0)
        self.assertAlmostEqual(style.opacity, 0.5)

    def test_current_style_without_fill(self):
        self.tab.fill_menu.set("Aucun")
        self.assertIsNone(self.tab._current_style().fill)

    def test_current_watermark_reads_the_panel(self):
        self.tab.watermark_var.set(True)
        self.tab.watermark_entry.delete(0, "end")
        self.tab.watermark_entry.insert(0, "BROUILLON")
        self.tab.wm_color_menu.set("Bleu")
        self.tab.wm_size_menu.set("80")
        self.tab.wm_opacity_menu.set("65 %")

        wm = self.tab._current_watermark()
        self.assertTrue(wm.enabled)
        self.assertEqual(wm.text, "BROUILLON")
        self.assertEqual(wm.color, COLORS["Bleu"])
        self.assertEqual(wm.size, 80.0)
        self.assertAlmostEqual(wm.opacity, 0.65)

    def test_blank_watermark_text_falls_back_to_confidentiel(self):
        self.tab.watermark_entry.delete(0, "end")
        self.tab.watermark_entry.insert(0, "   ")
        self.assertEqual(self.tab._current_watermark().text, "CONFIDENTIEL")

    def test_tk_font_covers_every_family_and_modifier(self):
        self.assertEqual(self.tab._tk_font(Style(family="helv", size=10))[0], "Helvetica")
        self.assertEqual(self.tab._tk_font(Style(family="tiro"))[0], "Times")
        self.assertEqual(self.tab._tk_font(Style(family="cour"))[0], "Courier")
        self.assertEqual(self.tab._tk_font(Style())[2], "normal")
        full = self.tab._tk_font(Style(bold=True, italic=True, underline=True))[2]
        self.assertIn("bold", full)
        self.assertIn("italic", full)
        self.assertIn("underline", full)


class TestEditorDrawing(_EditorTabTestCase):
    def test_press_without_document_warns(self):
        self.tab._on_press(_event(10, 10))
        self.assertIn("Ouvrez d'abord un PDF", self._log())

    def test_drag_before_press_is_ignored(self):
        self._load_pdf()
        self.tab._on_drag(_event(50, 50))
        self.assertIsNone(self.tab._rubber_band)

    def test_release_before_press_is_ignored(self):
        self._load_pdf()
        self.tab._on_release(_event(50, 50))
        self.assertEqual(self.tab.annotations, [])

    def test_drag_draws_then_replaces_the_rubber_band(self):
        self._load_pdf()
        self.tab.tool_var.set("rect")
        self.tab._on_press(_event(20, 20))
        self.tab._on_drag(_event(80, 90))
        first = self.tab._rubber_band
        self.assertIsNotNone(first)
        self.tab._on_drag(_event(120, 140))
        self.assertNotEqual(self.tab._rubber_band, first)

    def test_shape_tools_create_annotations(self):
        self._load_pdf()
        for kind in ("line", "arrow", "rect", "ellipse", "highlight"):
            self.tab.tool_var.set(kind)
            self.tab._on_press(_event(20, 20))
            self.tab._on_drag(_event(150, 160))
            self.tab._on_release(_event(150, 160))
        self.assertEqual([a.kind for a in self.tab.annotations],
                         ["line", "arrow", "rect", "ellipse", "highlight"])

    def test_click_without_dragging_is_rejected(self):
        self._load_pdf()
        self.tab.tool_var.set("rect")
        self.tab._on_press(_event(40, 40))
        self.tab._on_release(_event(41, 41))
        self.assertEqual(self.tab.annotations, [])
        self.assertIn("Glissez la souris", self._log())

    def test_text_tool_inserts_typed_content(self):
        self._load_pdf()
        self.tab.tool_var.set("text")
        dialog = MagicMock()
        dialog.get_input.return_value = "Bon pour accord"
        with patch("ui.tab_pdf_editor.ctk.CTkInputDialog", return_value=dialog):
            self.tab._on_press(_event(100, 200))
        self.assertEqual(len(self.tab.annotations), 1)
        self.assertEqual(self.tab.annotations[0].text, "Bon pour accord")

    def test_text_tool_cancelled_adds_nothing(self):
        self._load_pdf()
        self.tab.tool_var.set("text")
        dialog = MagicMock()
        dialog.get_input.return_value = ""
        with patch("ui.tab_pdf_editor.ctk.CTkInputDialog", return_value=dialog):
            self.tab._on_press(_event(100, 200))
        self.assertEqual(self.tab.annotations, [])

    def test_signature_tool_places_the_returned_image(self):
        self._load_pdf()
        sig = self.tmp_path / "sig.png"
        from PIL import Image
        Image.new("RGBA", (80, 40), (0, 0, 255, 255)).save(sig)

        self.tab.tool_var.set("signature")
        self.tab.wait_window = lambda dialog: None
        with patch("ui.tab_pdf_editor.SignatureDialog",
                   return_value=SimpleNamespace(result=str(sig))):
            self.tab._on_press(_event(300, 400))
            self.tab._on_release(_event(450, 480))

        self.assertEqual(len(self.tab.annotations), 1)
        self.assertEqual(self.tab.annotations[0].kind, "signature")
        self.assertEqual(self.tab.annotations[0].image_path, str(sig))

    def test_signature_dialog_cancelled_adds_nothing(self):
        self._load_pdf()
        self.tab.tool_var.set("signature")
        self.tab.wait_window = lambda dialog: None
        with patch("ui.tab_pdf_editor.SignatureDialog",
                   return_value=SimpleNamespace(result=None)):
            self.tab._on_press(_event(300, 400))
            self.tab._on_release(_event(450, 480))
        self.assertEqual(self.tab.annotations, [])


class TestEditorOverlay(_EditorTabTestCase):
    def test_overlay_draws_every_annotation_kind(self):
        self._load_pdf()
        sig = self.tmp_path / "sig.png"
        from PIL import Image
        Image.new("RGBA", (80, 40), (10, 10, 200, 255)).save(sig)

        self.tab.annotations = [
            Annotation("text", 0, 60, 100, text="Texte", style=Style(underline=True)),
            Annotation("line", 0, 50, 200, 300, 210),
            Annotation("arrow", 0, 50, 240, 300, 300),
            Annotation("rect", 0, 50, 330, 250, 420, style=Style(fill=COLORS["Jaune"])),
            Annotation("rect", 0, 260, 330, 400, 420, style=Style(fill=None)),
            Annotation("ellipse", 0, 50, 440, 250, 520, style=Style(fill=COLORS["Vert"])),
            Annotation("ellipse", 0, 260, 440, 400, 520, style=Style(fill=None)),
            Annotation("highlight", 0, 50, 540, 400, 570, style=Style(fill=COLORS["Jaune"])),
            Annotation("signature", 0, 350, 600, 500, 660, image_path=str(sig)),
            # Annotation d'une autre page : ne doit pas être dessinée ici.
            Annotation("text", 1, 10, 10, text="Autre page"),
        ]
        self.tab._render()
        self.assertGreater(len(self.tab.canvas.find_all()), 5)

    def test_broken_signature_falls_back_to_a_dashed_frame(self):
        self._load_pdf()
        self.tab.annotations = [
            Annotation("signature", 0, 100, 100, 250, 180,
                       image_path=str(self.tmp_path / "inexistant.png")),
        ]
        self.tab._render()  # ne doit pas lever
        self.assertGreater(len(self.tab.canvas.find_all()), 1)

    def test_preview_image_changes_when_watermark_is_enabled(self):
        # L'aperçu est produit par le moteur : cocher la case doit modifier
        # l'image elle-même, et le filigrane transmis doit être celui du panneau.
        self._load_pdf()
        captured = []
        real_render = self.tab.editor.render_page

        def spy(index, zoom=1.0, watermark=None):
            captured.append(watermark)
            return real_render(index, zoom, watermark)

        with patch.object(self.tab.editor, "render_page", spy):
            self.tab.watermark_var.set(False)
            self.tab._render()
            self.tab.watermark_var.set(True)
            self.tab.watermark_entry.delete(0, "end")
            self.tab.watermark_entry.insert(0, "INTERNE")
            self.tab._render()

        self.assertFalse(captured[0].enabled)
        self.assertTrue(captured[1].enabled)
        self.assertEqual(captured[1].text, "INTERNE")


class TestEditorActions(_EditorTabTestCase):
    def test_undo_removes_the_last_annotation(self):
        self._load_pdf()
        self.tab.annotations = [
            Annotation("text", 0, 10, 10, text="a"),
            Annotation("text", 0, 20, 20, text="b"),
        ]
        self.tab._undo()
        self.assertEqual([a.text for a in self.tab.annotations], ["a"])

    def test_undo_with_nothing_to_remove(self):
        self.tab._undo()
        self.assertIn("Rien à annuler", self._log())

    def test_clear_all_removes_everything(self):
        self._load_pdf()
        self.tab.annotations = [Annotation("text", 0, 10, 10, text="a")]
        self.tab._clear_all()
        self.assertEqual(self.tab.annotations, [])

    def test_clear_all_with_nothing_to_remove(self):
        self.tab._clear_all()
        self.assertIn("Aucune annotation", self._log())

    def test_save_without_document(self):
        self.tab._save()
        self.assertIn("Ouvrez d'abord un PDF", self._log())

    def test_save_with_nothing_to_write(self):
        self._load_pdf()
        self.tab._save()
        self.assertIn("Rien à enregistrer", self._log())

    def test_save_cancelled_at_dialog(self):
        self._load_pdf()
        self.tab.annotations = [Annotation("text", 0, 60, 100, text="Note")]
        with patch("ui.tab_pdf_editor.filedialog.asksaveasfilename", return_value=""):
            self.tab._save()
        self.assertNotIn("enregistré", self._log())

    def test_save_writes_annotations_and_watermark(self):
        self._load_pdf()
        self.tab.annotations = [
            Annotation("text", 0, 60, 100, text="Bon pour accord", style=Style(size=16)),
        ]
        self.tab.watermark_var.set(True)
        target = str(self.tmp_path / "signe.pdf")
        with patch("ui.tab_pdf_editor.filedialog.asksaveasfilename", return_value=target):
            self.tab._save()

        self.assertIn("PDF enregistré", self._log())
        import fitz
        doc = fitz.open(target)
        text = doc[0].get_text()
        doc.close()
        self.assertIn("Bon pour accord", text)
        self.assertIn("CONFIDENTIEL", text)

    def test_save_with_only_a_watermark_is_allowed(self):
        self._load_pdf()
        self.tab.watermark_var.set(True)
        target = str(self.tmp_path / "filigrane.pdf")
        with patch("ui.tab_pdf_editor.filedialog.asksaveasfilename", return_value=target):
            self.tab._save()
        self.assertTrue(Path(target).exists())

    def test_save_security_error_is_logged(self):
        self._load_pdf()
        self.tab.annotations = [Annotation("text", 0, 60, 100, text="Note")]
        with patch("ui.tab_pdf_editor.filedialog.asksaveasfilename",
                   return_value=str(self.tmp_path / "x.pdf")), \
             patch.object(self.tab.editor, "save", side_effect=SecurityError("refusé")):
            self.tab._save()
        self.assertIn("⛔ Sécurité", self._log())

    def test_save_generic_error_is_logged(self):
        self._load_pdf()
        self.tab.annotations = [Annotation("text", 0, 60, 100, text="Note")]
        with patch("ui.tab_pdf_editor.filedialog.asksaveasfilename",
                   return_value=str(self.tmp_path / "x.pdf")), \
             patch.object(self.tab.editor, "save", side_effect=RuntimeError("disque plein")):
            self.tab._save()
        self.assertIn("Erreur d'enregistrement", self._log())


if __name__ == "__main__":
    unittest.main()
