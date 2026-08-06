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


# ---------------------------------------------------- organisation des pages
def render_thumbnail(src: str, index: int, width: int = 130, password: str = "") -> bytes:
    """Rend une page en PNG à petite taille, pour un aperçu en vignette.

    Args:
        src: PDF source.
        index: index de page (0-based).
        width: largeur souhaitée en pixels ; la hauteur suit les proportions.
        password: mot de passe si le PDF est protégé.

    Returns:
        Les octets d'une image PNG.
    """
    import fitz

    doc = _open_document(src, password)
    try:
        page = doc[index]
        zoom = width / page.rect.width
        return page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
    finally:
        doc.close()


def organize_pages(
    src: str,
    output_path: str,
    pages: list[tuple[int, int]],
    password: str = "",
) -> str:
    """Réécrit le document avec les pages choisies, dans l'ordre et l'orientation voulus.

    Une seule primitive couvre les trois gestes : les pages absentes de la
    liste sont supprimées, l'ordre de la liste devient l'ordre du document, et
    chaque entrée porte sa propre rotation.

    Args:
        src: PDF source, jamais modifié.
        output_path: chemin souhaité (suffixé si déjà pris).
        pages: couples (index d'origine 0-based, rotation en degrés). Un même
            index peut apparaître plusieurs fois pour dupliquer une page.
        password: mot de passe si le PDF est protégé.

    Returns:
        Chemin du fichier généré.

    Raises:
        ValueError: liste vide, ou index de page hors bornes.
    """
    import fitz

    if not pages:
        raise ValueError("Le document doit conserver au moins une page.")

    doc = _open_document(src, password)
    try:
        total = len(doc)
        for index, _rotation in pages:
            if not 0 <= index < total:
                raise ValueError(f"Page inexistante : {index + 1} (1-{total})")

        result = fitz.open()
        try:
            for index, rotation in pages:
                result.insert_pdf(doc, from_page=index, to_page=index)
                # La rotation s'ajoute à celle déjà portée par la page : une
                # page déjà de travers dans le document d'origine doit pouvoir
                # être redressée par un quart de tour supplémentaire.
                page = result[-1]
                page.set_rotation((page.rotation + rotation) % 360)

            out = unique_path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            result.save(str(out))
        finally:
            result.close()
    finally:
        doc.close()
    return str(out)


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


# ---------------------------------------------------------------- extraction
def extract_text(src: str, output_path: str, password: str = "") -> tuple[str, int]:
    """Extrait le texte du PDF vers un fichier .txt ou .docx.

    Args:
        src: PDF source.
        output_path: chemin de sortie ; l'extension (.txt ou .docx) détermine
            le format produit.
        password: mot de passe si le PDF est protégé.

    Returns:
        (chemin généré, nombre de caractères extraits). Un total nul signale
        un PDF sans couche de texte — typiquement un scan, que seul un OCR
        pourrait exploiter : l'appelant doit pouvoir le dire à l'utilisateur
        plutôt que de livrer un fichier vide sans explication.

    Raises:
        ValueError: extension de sortie non supportée.
    """
    suffix = Path(output_path).suffix.lower()
    if suffix not in (".txt", ".docx"):
        raise ValueError(f"Format de sortie non supporté : {suffix} (.txt ou .docx)")

    doc = _open_document(src, password)
    try:
        pages = [page.get_text() for page in doc]
    finally:
        doc.close()

    out = unique_path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if suffix == ".txt":
        # Séparateur explicite : sans lui, deux pages se retrouvent collées et
        # l'on ne sait plus où l'une finit.
        body = "\n\n".join(
            f"--- Page {i + 1} ---\n{text}" for i, text in enumerate(pages))
        out.write_text(body, encoding="utf-8")
    else:
        from docx import Document

        document = Document()
        for i, text in enumerate(pages):
            document.add_heading(f"Page {i + 1}", level=2)
            for paragraph in text.split("\n"):
                document.add_paragraph(paragraph)
        document.save(str(out))

    return str(out), sum(len(text.strip()) for text in pages)


def extract_images(src: str, output_dir: str, password: str = "",
                   min_size: int = 64) -> list[str]:
    """Extrait les images embarquées du PDF, dans leur format d'origine.

    Ce sont bien les images stockées dans le document qui sont récupérées, et
    non un rendu des pages : la qualité d'origine est préservée.

    Args:
        src: PDF source.
        output_dir: dossier de destination.
        password: mot de passe si le PDF est protégé.
        min_size: taille minimale en octets ; en dessous, l'image est ignorée.
            Les PDF contiennent souvent des pixels de calage d'un octet ou
            deux, sans intérêt pour l'utilisateur.

    Returns:
        Chemins des images extraites, dans l'ordre des pages.
    """
    doc = _open_document(src, password)
    stem = Path(src).stem
    created: list[str] = []
    seen: set[int] = set()

    try:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        for number, page in enumerate(doc, start=1):
            for info in page.get_images(full=True):
                xref = info[0]
                # Une même image peut être posée sur plusieurs pages : on ne
                # l'extrait qu'une fois.
                if xref in seen:
                    continue
                seen.add(xref)

                data = doc.extract_image(xref)
                if len(data["image"]) < min_size:
                    continue
                out = unique_path(
                    Path(output_dir) / f"{stem}_p{number:02d}_{xref}.{data['ext']}")
                out.write_bytes(data["image"])
                created.append(str(out))
    finally:
        doc.close()
    return created


# ------------------------------------------------------- numérotation, entêtes
# Position du numéro de page : (alignement horizontal, en bas ou en haut).
NUMBER_POSITIONS = {
    "Bas centre": ("center", "bottom"),
    "Bas droite": ("right", "bottom"),
    "Bas gauche": ("left", "bottom"),
    "Haut centre": ("center", "top"),
    "Haut droite": ("right", "top"),
    "Haut gauche": ("left", "top"),
}

# Modèles de numérotation. {n} = numéro courant, {total} = nombre de pages.
NUMBER_FORMATS = ("{n}", "- {n} -", "Page {n}", "{n} / {total}", "Page {n} sur {total}")

MARGIN = 28.0  # distance au bord, en points PDF


def add_page_numbers(
    src: str,
    output_path: str,
    position: str = "Bas centre",
    number_format: str = "{n}",
    start_at: int = 1,
    skip_first: bool = False,
    font_size: float = 10.0,
    header: str = "",
    footer: str = "",
    password: str = "",
) -> str:
    """Ajoute une numérotation, et éventuellement un en-tête et un pied de page.

    Args:
        src: PDF source.
        output_path: chemin souhaité (suffixé si déjà pris).
        position: une clé de NUMBER_POSITIONS.
        number_format: modèle acceptant {n} et {total}. Vide = pas de numéro,
            ce qui permet de ne poser qu'un en-tête ou qu'un pied de page.
        start_at: numéro attribué à la première page numérotée.
        skip_first: laisse la première page sans numéro (page de garde).
        font_size: taille du texte ajouté.
        header, footer: textes libres, respectivement en haut et en bas.
        password: mot de passe si le PDF est protégé.

    Returns:
        Chemin du fichier généré.

    Raises:
        ValueError: position inconnue, ou modèle de numérotation invalide.
    """
    import fitz

    if position not in NUMBER_POSITIONS:
        raise ValueError(f"Position inconnue : {position}")

    align, vertical = NUMBER_POSITIONS[position]
    doc = _open_document(src, password)
    try:
        total = len(doc)

        def place(page, text: str, at_top: bool, alignment: str) -> None:
            """Écrit un texte sur une page, aligné et à distance du bord."""
            width = fitz.get_text_length(text, fontname="helv", fontsize=font_size)
            if alignment == "center":
                x = (page.rect.width - width) / 2
            elif alignment == "right":
                x = page.rect.width - MARGIN - width
            else:
                x = MARGIN
            y = MARGIN if at_top else page.rect.height - MARGIN + font_size / 2
            page.insert_text(fitz.Point(x, y), text,
                             fontname="helv", fontsize=font_size, color=(0, 0, 0))

        for index, page in enumerate(doc):
            if header:
                place(page, header, True, "center")
            if footer:
                place(page, footer, False, "left" if align != "left" else "right")

            if not number_format or (skip_first and index == 0):
                continue
            # La numérotation suit la position dans le document, mais démarre
            # au numéro choisi : un rapport peut commencer à « 1 » après une
            # page de garde non numérotée.
            number = start_at + index - (1 if skip_first else 0)
            try:
                text = number_format.format(n=number, total=total)
            except (KeyError, IndexError) as e:
                raise ValueError(
                    f"Modèle de numérotation invalide : {number_format} "
                    "(champs acceptés : {n} et {total})"
                ) from e
            place(page, text, vertical == "top", align)

        out = unique_path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out))
    finally:
        doc.close()
    return str(out)


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
