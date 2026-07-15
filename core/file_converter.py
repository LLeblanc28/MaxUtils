"""Conversion de fichiers multi-formats : images, vidéo, audio, documents,
tableurs et archives. 100 % local.
"""

import subprocess
import tarfile
import zipfile
from pathlib import Path
from typing import Callable

from PIL import Image

from utils.config import (
    ARCHIVE_EXTS,
    AUDIO_EXTS,
    DOC_EXTS,
    IMAGE_EXTS,
    PDF_EXTS,
    SHEET_EXTS,
    VIDEO_EXTS,
    get_ffmpeg_path,
)
from utils.helpers import unique_path

ProgressCb = Callable[[float, str], None] | None


def detect_category(path: str) -> str | None:
    """Détecte la catégorie d'un fichier selon son extension.

    Returns:
        "image", "video", "audio", "document", "sheet", "archive" ou None.
    """
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in DOC_EXTS:
        return "document"
    if ext in SHEET_EXTS:
        return "sheet"
    if ext in ARCHIVE_EXTS:
        return "archive"
    if ext in PDF_EXTS:
        return "pdf"
    return None


def convert_file(src: str, target_fmt: str, output_dir: str, cb: ProgressCb = None) -> str:
    """Convertit un fichier vers le format cible, en routant selon la catégorie.

    Args:
        src: fichier source.
        target_fmt: format cible (ex: "PNG", "MP4", "PDF", "EXTRAIRE").
        output_dir: dossier de sortie.
        cb: callback (progression 0-1, message).

    Returns:
        Chemin du fichier (ou dossier pour extraction) généré.

    Raises:
        ValueError: format non supporté.
        RuntimeError: ffmpeg introuvable ou échec de conversion.
    """
    category = detect_category(src)
    target = target_fmt.lower()
    if category == "image":
        return _convert_image(src, target, output_dir)
    if category in ("video", "audio"):
        return _convert_media(src, target, output_dir, cb)
    if category == "document":
        return _convert_document(src, output_dir)
    if category == "sheet":
        return _convert_sheet(src, target, output_dir)
    if category == "archive":
        return _handle_archive(src, target, output_dir)
    if category == "pdf":
        return _convert_pdf_to_images(src, target, output_dir, cb)
    raise ValueError(f"Format non supporté : {Path(src).suffix}")


# --------------------------------------------------------------------- images
def _convert_image(src: str, target: str, output_dir: str) -> str:
    """Convertit une image via Pillow (PDF inclus). Gère HEIC si pillow-heif présent."""
    if Path(src).suffix.lower() == ".heic":
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError as e:
            raise RuntimeError("Installez pillow-heif pour lire les fichiers HEIC.") from e

    img = Image.open(src)
    ext = "jpg" if target == "jpg" else target
    out = unique_path(Path(output_dir) / f"{Path(src).stem}.{ext}")

    if target in ("jpg", "pdf") and img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    save_fmt = {"jpg": "JPEG", "tiff": "TIFF"}.get(target, target.upper())
    img.save(out, format=save_fmt)
    return str(out)


# ---------------------------------------------------------------- vidéo/audio
def _convert_media(src: str, target: str, output_dir: str, cb: ProgressCb) -> str:
    """Convertit vidéo/audio via ffmpeg en sous-processus."""
    ffmpeg = get_ffmpeg_path()
    if not ffmpeg:
        raise RuntimeError("ffmpeg introuvable : installez-le ou ajoutez-le au PATH.")

    out = unique_path(Path(output_dir) / f"{Path(src).stem}.{target}")
    cmd = [ffmpeg, "-y", "-i", src]
    if target == "gif":
        cmd += ["-vf", "fps=12,scale=480:-1:flags=lanczos"]
    elif target == "mp3":
        cmd += ["-vn", "-b:a", "192k"]
    cmd.append(str(out))

    if cb:
        cb(0.1, f"Conversion de {Path(src).name}...")
    flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
    proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
    if proc.returncode != 0:
        raise RuntimeError(f"Échec ffmpeg : {proc.stderr[-400:]}")
    if cb:
        cb(1.0, f"Terminé : {out.name}")
    return str(out)


# ------------------------------------------------------------------ documents
def _convert_document(src: str, output_dir: str) -> str:
    """Convertit DOCX ou TXT vers PDF (docx2pdf / reportlab)."""
    ext = Path(src).suffix.lower()
    out = unique_path(Path(output_dir) / f"{Path(src).stem}.pdf")

    if ext == ".docx":
        try:
            from docx2pdf import convert
            convert(src, str(out))
        except Exception as e:
            raise RuntimeError(
                "Conversion DOCX→PDF impossible (Microsoft Word requis avec docx2pdf)."
            ) from e
        return str(out)

    # TXT → PDF via reportlab
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(out), pagesize=A4)
    width, height = A4
    y = height - 2 * cm
    with open(src, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            for chunk in [line.rstrip("\n")[i:i + 95] for i in range(0, max(len(line), 1), 95)]:
                c.drawString(2 * cm, y, chunk)
                y -= 14
                if y < 2 * cm:
                    c.showPage()
                    y = height - 2 * cm
    c.save()
    return str(out)


# ------------------------------------------------------------------- tableurs
def _convert_sheet(src: str, target: str, output_dir: str) -> str:
    """Convertit CSV ↔ XLSX via pandas."""
    import pandas as pd

    ext = Path(src).suffix.lower()
    out = unique_path(Path(output_dir) / f"{Path(src).stem}.{target}")
    if ext == ".csv" and target == "xlsx":
        pd.read_csv(src).to_excel(out, index=False)
    elif ext == ".xlsx" and target == "csv":
        pd.read_excel(src).to_csv(out, index=False)
    else:
        raise ValueError(f"Conversion tableur non supportée : {ext} → {target}")
    return str(out)


# ------------------------------------------------------------------ PDF→image
def _convert_pdf_to_images(src: str, target: str, output_dir: str, cb: ProgressCb) -> str:
    """Convertit chaque page d'un PDF en image (JPG/PNG) via PyMuPDF.

    Un PDF d'une page produit un seul fichier ; sinon un dossier contenant
    une image par page (nom_page01.png, ...).

    Returns:
        Chemin du fichier unique ou du dossier créé.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise RuntimeError("Installez PyMuPDF : pip install pymupdf") from e

    ext = "jpg" if target == "jpg" else "png"
    stem = Path(src).stem
    doc = fitz.open(src)
    n = len(doc)
    zoom = fitz.Matrix(2, 2)  # ~144 dpi, bonne qualité

    if n == 1:
        out = unique_path(Path(output_dir) / f"{stem}.{ext}")
        doc[0].get_pixmap(matrix=zoom).save(out)
        doc.close()
        return str(out)

    dest = unique_path(Path(output_dir) / f"{stem}_images")
    dest.mkdir(parents=True, exist_ok=True)
    for i, page in enumerate(doc):
        page.get_pixmap(matrix=zoom).save(dest / f"{stem}_page{i + 1:02d}.{ext}")
        if cb:
            cb((i + 1) / n, f"Page {i + 1}/{n}")
    doc.close()
    return str(dest)


# ------------------------------------------------------------------- archives
def _handle_archive(src: str, target: str, output_dir: str) -> str:
    """Extrait une archive (ZIP/TAR.GZ/7Z) ou recompresse en ZIP."""
    src_path = Path(src)
    ext = src_path.suffix.lower()

    if target == "extraire":
        dest = unique_path(Path(output_dir) / src_path.stem)
        dest.mkdir(parents=True, exist_ok=True)
        if ext == ".zip":
            with zipfile.ZipFile(src) as z:
                z.extractall(dest)
        elif ext in (".gz", ".tar"):
            with tarfile.open(src) as t:
                t.extractall(dest, filter="data")
        elif ext == ".7z":
            try:
                import py7zr
            except ImportError as e:
                raise RuntimeError("Installez py7zr pour extraire les archives 7z.") from e
            with py7zr.SevenZipFile(src) as z:
                z.extractall(dest)
        else:
            raise ValueError(f"Archive non supportée : {ext}")
        return str(dest)

    # Recompression en ZIP du contenu extrait ou du fichier seul
    out = unique_path(Path(output_dir) / f"{src_path.stem}.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(src, src_path.name)
    return str(out)
