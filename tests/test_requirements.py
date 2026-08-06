"""Vérifie que requirements.txt déclare bien tout ce que le code importe.

Une dépendance installée à la main mais oubliée dans requirements.txt ne se
voit pas : les tests passent sur la machine du développeur et l'application
casse partout ailleurs (CI, environnement recréé, exécutable distribué).
Ce test rend cet écart visible immédiatement.
"""

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Nom du module importé → nom du paquet à déclarer dans requirements.txt.
# Les deux diffèrent souvent (« docx » vient de « python-docx »).
MODULE_TO_PACKAGE = {
    "customtkinter": "customtkinter",
    "docx": "python-docx",
    "docx2pdf": "docx2pdf",
    "ffmpeg": "ffmpeg-python",
    "fitz": "pymupdf",
    "openpyxl": "openpyxl",
    "pandas": "pandas",
    "PIL": "Pillow",
    "pillow_heif": "pillow-heif",
    "py7zr": "py7zr",
    "pydub": "pydub",
    "pypdf": "pypdf",
    "reportlab": "reportlab",
    "tkinterdnd2": "tkinterdnd2",
    "yt_dlp": "yt-dlp",
}

# Modules de la bibliothèque standard ou internes au projet : jamais déclarés.
INTERNAL = {"core", "ui", "utils", "main"}


def _declared_packages() -> set[str]:
    """Noms des paquets listés dans requirements.txt, en minuscules."""
    packages = set()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # « docx2pdf==0.1.8; sys_platform == "win32" » → « docx2pdf »
        name = line.split(";")[0].split("==")[0].split(">=")[0].strip()
        packages.add(name.lower())
    return packages


def _imported_modules() -> set[str]:
    """Modules de premier niveau importés par le code applicatif."""
    modules = set()
    for folder in ("core", "ui", "utils"):
        for path in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    modules.add(node.module.split(".")[0])
    return modules - INTERNAL


class TestRequirementsAreComplete(unittest.TestCase):
    def test_every_third_party_import_is_declared(self):
        declared = _declared_packages()
        missing = sorted(
            package for module, package in MODULE_TO_PACKAGE.items()
            if module in _imported_modules() and package.lower() not in declared
        )
        self.assertEqual(
            missing, [],
            f"paquets importés par le code mais absents de requirements.txt : {missing}")

    def test_every_declared_package_is_pinned(self):
        # Une version non épinglée rend l'installation non reproductible et
        # rouvre le risque de supply-chain traité par l'audit de sécurité.
        unpinned = []
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "==" not in line:
                unpinned.append(line)
        self.assertEqual(unpinned, [], f"versions non épinglées : {unpinned}")

    def test_the_mapping_itself_stays_up_to_date(self):
        # Un import tiers absent de MODULE_TO_PACKAGE échapperait au contrôle
        # ci-dessus : on vérifie donc que la table couvre tout le non-standard.
        unknown = sorted(
            module for module in _imported_modules()
            if module not in MODULE_TO_PACKAGE
            and module not in sys.stdlib_module_names
        )
        self.assertEqual(
            unknown, [],
            f"imports tiers non répertoriés dans MODULE_TO_PACKAGE : {unknown}")


if __name__ == "__main__":
    unittest.main()
