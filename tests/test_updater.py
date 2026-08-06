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


if __name__ == "__main__":
    unittest.main()
