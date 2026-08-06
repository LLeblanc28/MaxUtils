"""Opérations sur un PDF entier : découpe, compression, protection.

Complète `pdf_merger` (assemblage) et `pdf_editor` (annotation) : ici on ne
modifie pas le contenu des pages, on agit sur le document lui-même.
Tout est local, et le fichier source n'est jamais écrasé.
"""

from pathlib import Path

from utils.helpers import parse_page_ranges, unique_path
from utils.security import check_file_size

# Réglages de compression PyMuPDF. `garbage=4` déduplique les objets, `clean`
# réécrit les flux de contenu, `deflate*` recompresse contenus, images et
# polices. L'effort ne change pas le rendu, seulement le temps de calcul.
COMPRESSION_LEVELS = {
    "Léger": {"garbage": 2, "deflate": True, "compression_effort": 0},
    "Normal": {"garbage": 4, "deflate": True, "deflate_images": True,
               "deflate_fonts": True, "clean": True, "compression_effort": 50},
    "Maximum": {"garbage": 4, "deflate": True, "deflate_images": True,
                "deflate_fonts": True, "clean": True, "compression_effort": 100},
}


def _open_document(path: str, password: str = ""):
    """Ouvre un PDF en refusant les fichiers trop gros ou verrouillés.

    Raises:
        SecurityError: fichier dépassant la taille maximale autorisée.
        ValueError: PDF protégé dont le mot de passe est absent ou incorrect.
    """
    import fitz

    check_file_size(path)
    doc = fitz.open(path)
    if doc.is_encrypted and not doc.authenticate(password):
        doc.close()
        raise ValueError(
            f"Le PDF « {Path(path).name} » est protégé par mot de passe."
            if not password
            else f"Mot de passe incorrect pour « {Path(path).name} »."
        )
    return doc


def page_count(path: str, password: str = "") -> int:
    """Nombre de pages d'un PDF, sans le charger durablement."""
    doc = _open_document(path, password)
    try:
        return len(doc)
    finally:
        doc.close()


# ------------------------------------------------------------------- découpe
def split_pdf(
    src: str,
    output_dir: str,
    page_ranges: str = "",
    per_page: bool = False,
    password: str = "",
) -> list[str]:
    """Extrait des pages vers un nouveau PDF, ou éclate le document page par page.

    Args:
        src: PDF source, jamais modifié.
        output_dir: dossier de destination.
        page_ranges: pages à retenir (ex. « 1-3,7 »). Vide = tout le document.
        per_page: si vrai, produit un fichier par page retenue ; sinon un seul
            fichier contenant les pages retenues, dans l'ordre demandé.
        password: mot de passe si le PDF est protégé.

    Returns:
        Liste des chemins créés, dans l'ordre de génération.

    Raises:
        ValueError: plage de pages invalide ou hors bornes.
        SecurityError: fichier source trop volumineux.
    """
    import fitz

    doc = _open_document(src, password)
    try:
        indices = parse_page_ranges(page_ranges, len(doc))
        stem = Path(src).stem
        created: list[str] = []

        if per_page:
            for index in indices:
                out = unique_path(Path(output_dir) / f"{stem}_page{index + 1:02d}.pdf")
                out.parent.mkdir(parents=True, exist_ok=True)
                single = fitz.open()
                try:
                    single.insert_pdf(doc, from_page=index, to_page=index)
                    single.save(str(out))
                finally:
                    single.close()
                created.append(str(out))
            return created

        out = unique_path(Path(output_dir) / f"{stem}_extrait.pdf")
        out.parent.mkdir(parents=True, exist_ok=True)
        extract = fitz.open()
        try:
            for index in indices:
                extract.insert_pdf(doc, from_page=index, to_page=index)
            extract.save(str(out))
        finally:
            extract.close()
        return [str(out)]
    finally:
        doc.close()


# --------------------------------------------------------------- compression
def compress_pdf(
    src: str,
    output_path: str,
    level: str = "Normal",
    password: str = "",
) -> tuple[str, int, int]:
    """Réécrit le PDF en le compressant, sans toucher au rendu des pages.

    Args:
        src: PDF source.
        output_path: chemin souhaité (suffixé si déjà pris).
        level: une clé de COMPRESSION_LEVELS.
        password: mot de passe si le PDF est protégé.

    Returns:
        (chemin généré, taille avant en octets, taille après en octets). La
        taille après peut être supérieure : un PDF déjà optimisé ne se
        comprime plus, et l'appelant doit pouvoir le signaler honnêtement.

    Raises:
        ValueError: niveau de compression inconnu.
    """
    if level not in COMPRESSION_LEVELS:
        raise ValueError(f"Niveau de compression inconnu : {level}")

    before = Path(src).stat().st_size
    doc = _open_document(src, password)
    try:
        out = unique_path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out), **COMPRESSION_LEVELS[level])
    finally:
        doc.close()
    return str(out), before, Path(out).stat().st_size


# ---------------------------------------------------------------- protection
def protect_pdf(
    src: str,
    output_path: str,
    password: str,
    allow_printing: bool = True,
    current_password: str = "",
) -> str:
    """Chiffre le PDF en AES-256 et exige un mot de passe à l'ouverture.

    Le chiffrement est délégué à PyMuPDF, déjà utilisé par l'application :
    l'AES-256 de pypdf réclamerait le paquet `cryptography` en plus, et son
    repli sans cette dépendance est le RC4, un algorithme cassé — inacceptable
    pour une fonction dont l'objet même est de protéger un document.

    Args:
        src: PDF source.
        output_path: chemin souhaité (suffixé si déjà pris).
        password: mot de passe demandé à l'ouverture.
        allow_printing: autorise ou non l'impression du document.
        current_password: mot de passe actuel si le PDF est déjà protégé.

    Returns:
        Chemin du fichier généré.

    Raises:
        ValueError: mot de passe vide, ou mot de passe actuel incorrect.
    """
    import fitz

    if not password:
        raise ValueError("Le mot de passe ne peut pas être vide.")

    doc = _open_document(src, current_password)
    try:
        permissions = fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_COPY
        if allow_printing:
            permissions |= fitz.PDF_PERM_PRINT | fitz.PDF_PERM_PRINT_HQ

        out = unique_path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(
            str(out),
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw=password,
            owner_pw=password,
            permissions=permissions,
        )
    finally:
        doc.close()
    return str(out)


def unlock_pdf(src: str, output_path: str, password: str) -> str:
    """Écrit une copie déchiffrée d'un PDF protégé, si le mot de passe est connu.

    Args:
        src: PDF protégé.
        output_path: chemin souhaité (suffixé si déjà pris).
        password: mot de passe d'ouverture du document.

    Returns:
        Chemin du fichier généré, ouvrable sans mot de passe.

    Raises:
        ValueError: document non protégé, ou mot de passe incorrect.
    """
    import fitz

    check_file_size(src)
    doc = fitz.open(src)
    try:
        if not doc.is_encrypted:
            raise ValueError(f"« {Path(src).name} » n'est pas protégé par mot de passe.")
        if not doc.authenticate(password):
            raise ValueError(f"Mot de passe incorrect pour « {Path(src).name} ».")

        out = unique_path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out), encryption=fitz.PDF_ENCRYPT_NONE)
    finally:
        doc.close()
    return str(out)
