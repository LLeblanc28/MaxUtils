"""Tests de la traduction de l'interface (utils/i18n.py).

Le point délicat n'est pas la traduction elle-même mais le retour : plusieurs
menus utilisent les libellés français comme clés de dictionnaire. Si
`untranslate` ne rendait pas exactement la clé d'origine, une sélection en
anglais ne correspondrait plus à aucune entrée et l'application planterait.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pdf_editor import COLORS
from core.pdf_tools import COMPRESSION_LEVELS
from core.video_downloader import SUBTITLE_LANGUAGES
from utils import i18n
from utils.i18n import TRANSLATIONS, get_language, set_language, t, tl, untranslate


class _LanguageTestCase(unittest.TestCase):
    """Restaure la langue après chaque test : l'état est global au module."""

    def setUp(self):
        self._previous = get_language()

    def tearDown(self):
        set_language(self._previous)


class TestSetLanguage(_LanguageTestCase):
    def test_default_is_french(self):
        self.assertEqual(i18n._current, "fr")

    def test_switching_to_english(self):
        set_language("en")
        self.assertEqual(get_language(), "en")

    def test_unknown_language_falls_back_to_french(self):
        set_language("klingon")
        self.assertEqual(get_language(), "fr")


class TestTranslate(_LanguageTestCase):
    def test_french_returns_the_key_unchanged(self):
        set_language("fr")
        self.assertEqual(t("Télécharger"), "Télécharger")

    def test_english_returns_the_translation(self):
        set_language("en")
        self.assertEqual(t("Télécharger"), "Download")

    def test_untranslated_string_is_shown_as_is(self):
        # Une chaîne oubliée doit rester lisible plutôt que casser l'affichage.
        set_language("en")
        self.assertEqual(t("Chaîne jamais traduite"), "Chaîne jamais traduite")

    def test_placeholders_survive_translation(self):
        set_language("en")
        self.assertEqual(t("Erreur : {error}").format(error="boum"), "Error: boum")

    def test_tl_translates_a_whole_menu(self):
        set_language("en")
        self.assertEqual(tl(["Noir", "Rouge"]), ["Black", "Red"])

    def test_tl_accepts_a_dictionary_and_keeps_the_order(self):
        set_language("en")
        self.assertEqual(tl({"Noir": 1, "Rouge": 2}), ["Black", "Red"])


class TestUntranslate(_LanguageTestCase):
    def test_in_french_the_value_is_already_the_key(self):
        set_language("fr")
        self.assertEqual(untranslate("Rouge"), "Rouge")

    def test_english_label_maps_back_to_the_french_key(self):
        set_language("en")
        self.assertEqual(untranslate("Red"), "Rouge")

    def test_unknown_label_is_returned_unchanged(self):
        set_language("en")
        self.assertEqual(untranslate("Chartreuse"), "Chartreuse")

    def test_every_colour_survives_the_round_trip(self):
        # Ces libellés servent de clés dans COLORS : un aller-retour incorrect
        # provoquerait un KeyError au moment de dessiner.
        set_language("en")
        for french in COLORS:
            self.assertEqual(untranslate(t(french)), french)

    def test_every_compression_level_survives_the_round_trip(self):
        set_language("en")
        for french in COMPRESSION_LEVELS:
            self.assertEqual(untranslate(t(french)), french)

    def test_every_subtitle_language_survives_the_round_trip(self):
        set_language("en")
        for french in SUBTITLE_LANGUAGES:
            self.assertEqual(untranslate(t(french)), french)

    def test_image_options_survive_the_round_trip(self):
        from ui.tab_converter import IMAGE_QUALITIES, IMAGE_WIDTHS

        set_language("en")
        for french in list(IMAGE_WIDTHS) + list(IMAGE_QUALITIES):
            self.assertEqual(untranslate(t(french)), french)


class TestNoFrenchTextLeaksInEnglish(_LanguageTestCase):
    """Parcourt l'interface complète en anglais et signale tout libellé resté
    en français alors qu'une traduction existe.

    Ce test attrape la classe d'oubli la plus facile à commettre : une chaîne
    passée par une variable ou un paramètre, que l'on croit traduite parce que
    ses voisines le sont.
    """

    def _all_texts(self, widget, found):
        for child in widget.winfo_children():
            try:
                text = child.cget("text")
            except Exception:
                text = None
            if isinstance(text, str) and text:
                found.append(text)
            self._all_texts(child, found)

    def test_every_visible_label_is_translated(self):
        import tempfile
        from unittest.mock import patch

        set_language("en")
        from ui.app import MultiToolApp

        with patch("ui.app.load_config", return_value={
                       "theme": "dark", "language": "en",
                       "output_dir": tempfile.gettempdir()}), \
             patch("ui.app.save_config"):
            app = MultiToolApp()
        try:
            app.update()
            texts = []
            self._all_texts(app, texts)
            self.assertGreater(len(texts), 30, "interface anormalement vide")

            translatable = {key for key, value in TRANSLATIONS.items() if key != value}
            leaked = sorted({text for text in texts if text in translatable})
            self.assertEqual(leaked, [], f"libellés restés en français : {leaked}")
        finally:
            app.destroy()


class TestBindMemory(_LanguageTestCase):
    """La mémoire des réglages doit stocker la clé française, jamais le libellé
    affiché : sinon un choix fait en anglais serait perdu au retour au
    français, et inversement."""

    @classmethod
    def setUpClass(cls):
        import customtkinter as ctk

        cls.root = ctk.CTk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _menu(self, values):
        import customtkinter as ctk

        return ctk.CTkOptionMenu(self.root, values=values)

    def test_nothing_happens_without_an_app_memory(self):
        from types import SimpleNamespace

        from ui.widgets import bind_memory

        menu = self._menu(["Noir", "Rouge"])
        bind_memory(SimpleNamespace(), menu, "cle")   # ne doit pas lever
        menu.destroy()

    def test_stored_value_is_restored(self):
        from types import SimpleNamespace

        from ui.widgets import bind_memory

        store = {"cle": "Rouge"}
        app = SimpleNamespace(recall=lambda k, d="": store.get(k, d),
                              remember=lambda k, v: store.__setitem__(k, v))
        menu = self._menu(["Noir", "Rouge"])
        bind_memory(app, menu, "cle")
        self.assertEqual(menu.get(), "Rouge")
        menu.destroy()

    def test_a_stale_value_is_ignored(self):
        from types import SimpleNamespace

        from ui.widgets import bind_memory

        app = SimpleNamespace(recall=lambda k, d="": "Chartreuse",
                              remember=lambda k, v: None)
        menu = self._menu(["Noir", "Rouge"])
        menu.set("Noir")
        bind_memory(app, menu, "cle")
        self.assertEqual(menu.get(), "Noir")   # la valeur devenue invalide est écartée
        menu.destroy()

    def test_choice_is_stored_under_its_french_key(self):
        from types import SimpleNamespace

        from ui.widgets import bind_memory

        store = {}
        app = SimpleNamespace(recall=lambda k, d="": store.get(k, d),
                              remember=lambda k, v: store.__setitem__(k, v))
        set_language("en")
        menu = self._menu(tl(["Noir", "Rouge"]))
        bind_memory(app, menu, "cle")
        menu._command("Red")
        self.assertEqual(store["cle"], "Rouge")
        menu.destroy()

    def test_a_value_stored_in_french_is_shown_translated(self):
        from types import SimpleNamespace

        from ui.widgets import bind_memory

        app = SimpleNamespace(recall=lambda k, d="": "Rouge",
                              remember=lambda k, v: None)
        set_language("en")
        menu = self._menu(tl(["Noir", "Rouge"]))
        bind_memory(app, menu, "cle")
        self.assertEqual(menu.get(), "Red")
        menu.destroy()

    def test_an_existing_command_is_preserved(self):
        from types import SimpleNamespace

        from ui.widgets import bind_memory

        calls = []
        app = SimpleNamespace(recall=lambda k, d="": "", remember=lambda k, v: None)
        menu = self._menu(["Noir", "Rouge"])
        menu.configure(command=calls.append)
        bind_memory(app, menu, "cle")
        menu._command("Rouge")
        self.assertEqual(calls, ["Rouge"])   # le comportement d'origine subsiste
        menu.destroy()


class TestTranslationTable(unittest.TestCase):
    def test_no_translation_is_left_empty(self):
        empty = [key for key, value in TRANSLATIONS.items() if not value.strip()]
        self.assertEqual(empty, [])

    def test_placeholders_match_between_both_languages(self):
        # Un champ nommé différemment en anglais provoquerait un KeyError à
        # l'exécution, au moment du .format().
        import re

        mismatches = []
        for french, english in TRANSLATIONS.items():
            if set(re.findall(r"{(\w+)}", french)) != set(re.findall(r"{(\w+)}", english)):
                mismatches.append(french)
        self.assertEqual(mismatches, [])


if __name__ == "__main__":
    unittest.main()
