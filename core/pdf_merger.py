"""Logique d'assemblage de fichiers PDF (fusion, plages de pages, rotation).

Basé sur pypdf. Toutes les opérations sont locales.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pypdf import PdfReader, PdfWriter

from utils.helpers import parse_page_ranges, unique_path
from utils.security import check_file_size


def _open_reader(path: str) -> PdfReader:
    """Ouvre un PDF, en détectant explicitement les fichiers protégés.

    Un PDF chiffré nécessitant un vrai mot de passe est signalé clairement au
    lieu d'être fusionné silencieusement avec des pages vides/corrompues.

    Raises:
        SecurityError: fichier trop volumineux.
        ValueError: PDF protégé par un mot de passe non vide.
    """
    check_file_size(path)
    reader = PdfReader(path)
    if reader.is_encrypted:
        result = reader.decrypt("")
        if not result:
            raise ValueError(
                f"Le PDF « {Path(path).name} » est protégé par mot de passe "
                "et ne peut pas être fusionné."
            )
    return reader


@dataclass
class PdfItem:
    """Représente un PDF dans la liste de fusion.

    Attributes:
        path: chemin du fichier.
        page_range: spécification de pages (ex: "1-3,5"). Vide = tout.
        rotation: rotation appliquée à toutes les pages retenues (0/90/180/270).
    """

    path: str
    page_range: str = ""
    rotation: int = 0
    _num_pages: int = field(default=-1, repr=False)

    @property
    def num_pages(self) -> int:
        """Nombre de pages du PDF (mis en cache après première lecture).

        Raises:
            SecurityError: fichier trop volumineux.
            ValueError: PDF protégé par un mot de passe non vide.
        """
        if self._num_pages < 0:
            self._num_pages = len(_open_reader(self.path).pages)
        return self._num_pages

    @property
    def name(self) -> str:
        return Path(self.path).name


def merge_pdfs(
    items: list[PdfItem],
    output_path: str,
    progress_callback: Callable[[float, str], None] | None = None,
) -> str:
    """Fusionne une liste de PdfItem en un seul PDF.

    Args:
        items: fichiers dans l'ordre de fusion, avec plages et rotations.
        output_path: chemin du PDF de sortie.
        progress_callback: fonction (progression 0-1, message) appelée pendant
            la fusion, ou None.

    Returns:
        Chemin réel du fichier généré.

    Raises:
        ValueError: liste vide, plage de pages invalide, ou PDF protégé par mot de passe.
        SecurityError: fichier source trop volumineux.
    """
    if not items:
        raise ValueError("Aucun fichier PDF à fusionner.")

    writer = PdfWriter()
    total = len(items)

    for i, item in enumerate(items):
        reader = _open_reader(item.path)
        indices = parse_page_ranges(item.page_range, len(reader.pages))
        for idx in indices:
            page = reader.pages[idx]
            if item.rotation:
                page.rotate(item.rotation)
            writer.add_page(page)
        if progress_callback:
            progress_callback((i + 1) / total, f"Ajout de {item.name}")

    out = unique_path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        writer.write(f)

    if progress_callback:
        progress_callback(1.0, f"Fusion terminée : {out.name}")
    return str(out)
