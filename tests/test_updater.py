"""Tests de la mise à jour de yt-dlp (core/updater.py).

Aucun test n'installe réellement de paquet : `subprocess.run` est simulé, ce
qui permet de couvrir les cas d'échec (réseau, délai, pip absent) sans
dépendre d'une connexion ni modifier l'environnement.
"""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import updater


class TestCurrentVersion(unittest.TestCase):
    def test_returns_the_installed_version(self):
        version = updater.current_version()
        self.assertIsInstance(version, str)
        self.assertNotEqual(version, "")

    def test_unknown_when_yt_dlp_cannot_be_read(self):
        with patch.dict(sys.modules, {"yt_dlp": None}):
            self.assertEqual(updater.current_version(), "inconnue")


class TestIsFrozen(unittest.TestCase):
    def test_false_when_running_from_sources(self):
        self.assertFalse(updater.is_frozen())

    def test_true_when_packaged_by_pyinstaller(self):
        with patch.object(updater.sys, "frozen", True, create=True):
            self.assertTrue(updater.is_frozen())


class TestUpdateYtDlp(unittest.TestCase):
    def test_refused_and_explained_when_packaged(self):
        # Dans un .exe PyInstaller, pip n'existe pas : mieux vaut l'expliquer
        # que de lancer une commande vouée à échouer avec un message obscur.
        with patch.object(updater, "is_frozen", return_value=True):
            ok, message = updater.update_yt_dlp()
        self.assertFalse(ok)
        self.assertIn("exécutable", message)

    def test_successful_update_asks_for_a_restart(self):
        result = MagicMock(returncode=0, stdout="Successfully installed yt-dlp-2026.9.1", stderr="")
        with patch.object(updater.subprocess, "run", return_value=result):
            ok, message = updater.update_yt_dlp()
        self.assertTrue(ok)
        self.assertIn("Redémarrez", message)

    def test_already_up_to_date_is_reported_as_success(self):
        result = MagicMock(returncode=0, stdout="Requirement already satisfied", stderr="")
        with patch.object(updater.subprocess, "run", return_value=result):
            ok, message = updater.update_yt_dlp()
        self.assertTrue(ok)
        self.assertIn("déjà à jour", message)

    def test_pip_failure_surfaces_its_error(self):
        result = MagicMock(returncode=1, stdout="", stderr="ERROR: no network")
        with patch.object(updater.subprocess, "run", return_value=result):
            ok, message = updater.update_yt_dlp()
        self.assertFalse(ok)
        self.assertIn("no network", message)

    def test_timeout_is_reported_without_traceback(self):
        with patch.object(updater.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("pip", 180)):
            ok, message = updater.update_yt_dlp()
        self.assertFalse(ok)
        self.assertIn("délai", message)

    def test_missing_interpreter_is_reported(self):
        with patch.object(updater.subprocess, "run", side_effect=OSError("introuvable")):
            ok, message = updater.update_yt_dlp()
        self.assertFalse(ok)
        self.assertIn("impossible", message)

    def test_pip_is_invoked_on_the_running_interpreter(self):
        # Installer dans un autre interpréteur que celui en cours mettrait à
        # jour un environnement qui n'est pas celui de l'application.
        result = MagicMock(returncode=0, stdout="Successfully installed", stderr="")
        with patch.object(updater.subprocess, "run", return_value=result) as run:
            updater.update_yt_dlp()
        command = run.call_args[0][0]
        self.assertEqual(command[:4], [sys.executable, "-m", "pip", "install"])
        self.assertIn("yt-dlp", command)


class TestParseVersion(unittest.TestCase):
    def test_plain_version(self):
        self.assertEqual(updater.parse_version("1.2.3"), (1, 2, 3))

    def test_leading_v_is_ignored(self):
        self.assertEqual(updater.parse_version("v2.0.1"), (2, 0, 1))

    def test_suffix_is_dropped(self):
        self.assertEqual(updater.parse_version("v1.4.0-beta"), (1, 4, 0))

    def test_comparison_orders_versions_correctly(self):
        self.assertGreater(updater.parse_version("1.10.0"), updater.parse_version("1.9.0"))
        self.assertGreater(updater.parse_version("2.0.0"), updater.parse_version("1.99.99"))
        self.assertEqual(updater.parse_version("1.0.0"), updater.parse_version("v1.0.0"))

    def test_unparseable_text_gives_an_empty_tuple(self):
        self.assertEqual(updater.parse_version("inconnue"), ())


class TestCheckAppUpdate(unittest.TestCase):
    def _respond(self, payload: dict):
        """Simule la réponse JSON de l'API GitHub."""
        import io
        import json
        from contextlib import contextmanager

        @contextmanager
        def fake_urlopen(request, timeout=None):
            yield io.BytesIO(json.dumps(payload).encode("utf-8"))

        return patch.object(updater.urllib.request, "urlopen", fake_urlopen)

    def test_newer_version_is_announced_with_the_link(self):
        with self._respond({"tag_name": "v2.0.0"}):
            available, message = updater.check_app_update("1.0.0")
        self.assertTrue(available)
        self.assertIn("2.0.0", message)
        self.assertIn("github.com", message)

    def test_same_version_reports_up_to_date(self):
        with self._respond({"tag_name": "v1.0.0"}):
            available, message = updater.check_app_update("1.0.0")
        self.assertFalse(available)
        self.assertIn("dernière version", message)

    def test_older_published_version_is_not_offered(self):
        with self._respond({"tag_name": "v0.9.0"}):
            available, _ = updater.check_app_update("1.0.0")
        self.assertFalse(available)

    def test_no_release_yet(self):
        with self._respond({}):
            available, message = updater.check_app_update("1.0.0")
        self.assertFalse(available)
        self.assertIn("Aucune version", message)

    def test_offline_is_explained_without_a_traceback(self):
        with patch.object(updater.urllib.request, "urlopen",
                          side_effect=updater.urllib.error.URLError("pas de réseau")):
            available, message = updater.check_app_update("1.0.0")
        self.assertFalse(available)
        self.assertIn("connexion", message)

    def test_missing_repository_is_explained(self):
        error = updater.urllib.error.HTTPError(
            updater.RELEASES_URL, 404, "Not Found", {}, None)
        with patch.object(updater.urllib.request, "urlopen", side_effect=error):
            available, message = updater.check_app_update("1.0.0")
        self.assertFalse(available)
        self.assertIn("Aucune version", message)

    def test_other_http_errors_are_reported(self):
        error = updater.urllib.error.HTTPError(
            updater.RELEASES_URL, 503, "Unavailable", {}, None)
        with patch.object(updater.urllib.request, "urlopen", side_effect=error):
            available, message = updater.check_app_update("1.0.0")
        self.assertFalse(available)
        self.assertIn("503", message)

    def test_malformed_response_is_reported(self):
        import io
        from contextlib import contextmanager

        @contextmanager
        def broken(request, timeout=None):
            yield io.BytesIO(b"ceci n'est pas du JSON")

        with patch.object(updater.urllib.request, "urlopen", broken):
            available, message = updater.check_app_update("1.0.0")
        self.assertFalse(available)
        self.assertIn("impossible", message)

    def test_timeout_is_reported(self):
        with patch.object(updater.urllib.request, "urlopen", side_effect=TimeoutError()):
            available, message = updater.check_app_update("1.0.0")
        self.assertFalse(available)
        self.assertIn("connexion", message)

    def test_no_user_data_is_sent(self):
        # La requête ne doit contenir que l'adresse publique du dépôt.
        captured = {}
        import io
        from contextlib import contextmanager

        @contextmanager
        def capture(request, timeout=None):
            captured["url"] = request.full_url
            captured["data"] = request.data
            yield io.BytesIO(b'{"tag_name": "v1.0.0"}')

        with patch.object(updater.urllib.request, "urlopen", capture):
            updater.check_app_update("1.0.0")

        self.assertEqual(captured["url"], updater.RELEASES_URL)
        self.assertIsNone(captured["data"])


if __name__ == "__main__":
    unittest.main()
