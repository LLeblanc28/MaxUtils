"""Couvre les branches non exercées de utils/config.py, utils/helpers.py et
utils/security.py : get_ffmpeg_path (réel + fallback), resource_path avec
_MEIPASS, open_in_explorer (3 plateformes), human_size (PB), unique_path
(double collision), validate_url (hôte vide), verify_file_signature (webp)."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import utils.config as config_mod
import utils.helpers as helpers
from utils.security import SecurityError, validate_url, verify_file_signature


class TestResourcePathAndFfmpeg(unittest.TestCase):
    def test_resource_path_uses_meipass_when_present(self):
        with patch.object(config_mod.sys, "_MEIPASS", "C:/fake_bundle", create=True):
            result = config_mod.resource_path("bin/ffmpeg.exe")
        self.assertTrue(result.startswith("C:/fake_bundle") or result.startswith("C:\\fake_bundle"))

    def test_get_ffmpeg_path_finds_project_bin_folder(self):
        # bin/ est gitignored (téléchargé par install.bat) : absent sur un
        # checkout CI propre. On crée un binaire factice pour le test, sans
        # toucher à un éventuel vrai ffmpeg.exe déjà présent en local.
        exe_name = "ffmpeg.exe" if config_mod.os.name == "nt" else "ffmpeg"
        project_root = Path(config_mod.__file__).resolve().parent.parent
        bin_dir = project_root / "bin"
        fake_ffmpeg = bin_dir / exe_name

        bin_dir_created = not bin_dir.exists()
        bin_dir.mkdir(parents=True, exist_ok=True)
        ffmpeg_already_existed = fake_ffmpeg.exists()
        if not ffmpeg_already_existed:
            fake_ffmpeg.write_bytes(b"fake ffmpeg binary for tests")

        try:
            result = config_mod.get_ffmpeg_path()
            self.assertIsNotNone(result)
            self.assertTrue(result.endswith(exe_name))
        finally:
            if not ffmpeg_already_existed:
                fake_ffmpeg.unlink()
            if bin_dir_created:
                bin_dir.rmdir()

    def test_get_ffmpeg_path_falls_back_to_path_lookup(self):
        with patch.object(config_mod.Path, "is_file", return_value=False), \
             patch.object(config_mod.shutil, "which", return_value="/usr/bin/ffmpeg"):
            result = config_mod.get_ffmpeg_path()
        self.assertEqual(result, "/usr/bin/ffmpeg")

    def test_get_ffmpeg_path_returns_none_when_not_found(self):
        with patch.object(config_mod.Path, "is_file", return_value=False), \
             patch.object(config_mod.shutil, "which", return_value=None):
            result = config_mod.get_ffmpeg_path()
        self.assertIsNone(result)


class TestOpenInExplorer(unittest.TestCase):
    def test_windows_uses_explorer_select(self):
        with patch.object(helpers.platform, "system", return_value="Windows"), \
             patch.object(helpers.subprocess, "Popen") as mock_popen:
            helpers.open_in_explorer("C:/dossier/fichier.pdf")
        args = mock_popen.call_args[0][0]
        self.assertEqual(args[0], "explorer")
        self.assertIn("/select,", args[1])

    def test_macos_uses_open_dash_r(self):
        with patch.object(helpers.platform, "system", return_value="Darwin"), \
             patch.object(helpers.subprocess, "Popen") as mock_popen:
            helpers.open_in_explorer("/tmp/fichier.pdf")
        mock_popen.assert_called_once_with(["open", "-R", "/tmp/fichier.pdf"])

    def test_linux_uses_xdg_open_on_parent_dir(self):
        with patch.object(helpers.platform, "system", return_value="Linux"), \
             patch.object(helpers.subprocess, "Popen") as mock_popen:
            helpers.open_in_explorer("/tmp/dossier/fichier.pdf")
        args = mock_popen.call_args[0][0]
        self.assertEqual(args[0], "xdg-open")
        self.assertEqual(Path(args[1]), Path("/tmp/dossier"))


class TestHumanSizeAndUniquePath(unittest.TestCase):
    def test_human_size_petabyte_range(self):
        self.assertEqual(helpers.human_size(1024**5 * 2), "2.0 PB")

    def test_unique_path_increments_past_first_collision(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir) / "file.txt"
            base.write_text("a", encoding="utf-8")
            (Path(tmp_dir) / "file_1.txt").write_text("b", encoding="utf-8")
            result = helpers.unique_path(base)
            self.assertEqual(result.name, "file_2.txt")


class TestSecurityRemainingBranches(unittest.TestCase):
    def test_validate_url_scheme_present_but_no_hostname(self):
        with self.assertRaises(SecurityError):
            validate_url("http://")

    def test_verify_file_signature_webp_accepted(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f = Path(tmp_dir) / "img.webp"
            f.write_bytes(b"RIFF\x00\x00\x00\x00WEBPVP8 ")
            self.assertTrue(verify_file_signature(str(f)))

    def test_verify_file_signature_webp_rejected(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f = Path(tmp_dir) / "img.webp"
            f.write_bytes(b"NOTRIFFxxxxNOTWEBP")
            self.assertFalse(verify_file_signature(str(f)))


if __name__ == "__main__":
    unittest.main()
