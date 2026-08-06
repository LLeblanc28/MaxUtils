"""Traduction de l'interface (français / anglais).

Le français est la langue de référence : les clés de traduction *sont* les
chaînes françaises. Une chaîne sans traduction anglaise est donc affichée
telle quelle plutôt que de faire échouer l'affichage — un texte non traduit
reste préférable à une interface cassée.

Usage :
    from utils.i18n import t
    ctk.CTkLabel(parent, text=t("Enregistrer"))
"""

LANGUAGES = ("fr", "en")

_current = "fr"

# Clé française → traduction anglaise.
TRANSLATIONS: dict[str, str] = {
    # --- Fenêtre principale et paramètres -------------------------------
    "🛠️ Multi-Outils": "🛠️ Multi-Tools",
    "📥 Vidéo": "📥 Video",
    "🔄 Convertisseur": "🔄 Converter",
    "📄 Fusion PDF": "📄 Merge PDF",
    "✏️ Éditeur PDF": "✏️ PDF Editor",
    "🧰 Outils PDF": "🧰 PDF Tools",
    "Paramètres": "Settings",
    "Thème :": "Theme:",
    "Langue :": "Language:",
    "Dossier de sortie :": "Output folder:",
    "Parcourir...": "Browse...",
    "Téléchargeur vidéo :": "Video downloader:",
    "Mettre à jour yt-dlp": "Update yt-dlp",
    "Mise à jour en cours...": "Updating...",
    "Application :": "Application:",
    "Vérifier les mises à jour": "Check for updates",
    "Vérification en cours...": "Checking...",
    "Le changement de langue s'applique au redémarrage.":
        "The language change takes effect after a restart.",

    # --- Onglet Vidéo ----------------------------------------------------
    "Collez une URL (YouTube, TikTok, Vimeo...)":
        "Paste a URL (YouTube, TikTok, Vimeo...)",
    "Détecter": "Detect",
    "MP4 (vidéo)": "MP4 (video)",
    "MP3 (audio)": "MP3 (audio)",
    "Toute la playlist": "Entire playlist",
    "Sous-titres :": "Subtitles:",
    "Extrait de": "Clip from",
    "à": "to",
    "Télécharger": "Download",
    "Annuler": "Cancel",
    "Veuillez saisir une URL.": "Please enter a URL.",
    "Téléchargement en {format}...": "Downloading as {format}...",
    "➕ À la file": "➕ To queue",
    "Vider la file": "Clear queue",
    "File d'attente : {count} URL": "Queue: {count} URL",
    "Ajouté à la file ({count} au total).": "Added to queue ({count} in total).",
    "Cette URL est déjà dans la file.": "This URL is already in the queue.",
    "[{position}/{total}] {url}": "[{position}/{total}] {url}",
    "File terminée : {count} fichier(s).": "Queue finished: {count} file(s).",
    "Terminé : {path}": "Done: {path}",
    "Terminé : {count} fichiers dans {folder}": "Done: {count} files in {folder}",
    "⛔ URL refusée : {error}": "⛔ URL refused: {error}",
    "⛔ Sécurité : {error}": "⛔ Security: {error}",
    "Erreur : {error}": "Error: {error}",
    "Récupération des informations...": "Fetching information...",
    "Informations récupérées.": "Information retrieved.",
    "Téléchargement annulé.": "Download cancelled.",
    "Aucun": "None",
    "Français": "French",
    "Anglais": "English",
    "Espagnol": "Spanish",
    "Allemand": "German",
    "Italien": "Italian",

    # --- Onglet Convertisseur -------------------------------------------
    "➕ Ajouter des fichiers": "➕ Add files",
    "🗑 Vider la liste": "🗑 Clear list",
    "Fichiers à convertir  —  ou glissez-les ici":
        "Files to convert  —  or drop them here",
    "Format cible :": "Target format:",
    "Convertir tout": "Convert all",
    "Images —  largeur max :": "Images —  max width:",
    "qualité :": "quality:",
    "Taille d'origine": "Original size",
    "Par défaut": "Default",
    "Maximale (95)": "Maximum (95)",
    "Élevée (85)": "High (85)",
    "Moyenne (70)": "Medium (70)",
    "Réduite (50)": "Low (50)",
    "Aucun fichier à convertir.": "No file to convert.",
    "Choisissez un format cible.": "Choose a target format.",
    "Conversion terminée.": "Conversion complete.",
    "Format non supporté : {name}": "Unsupported format: {name}",
    "⛔ {name} refusé (sécurité) : {error}": "⛔ {name} refused (security): {error}",

    # --- Onglet Fusion PDF ----------------------------------------------
    "➕ Ajouter des PDF": "➕ Add PDFs",
    "PDF à fusionner (ordre = ordre de fusion)  —  ou glissez-les ici":
        "PDFs to merge (order = merge order)  —  or drop them here",
    "Sortie :": "Output:",
    "Fusionner": "Merge",
    "Ouvrir le fichier généré": "Open generated file",
    "Ajoutez au moins un PDF.": "Add at least one PDF.",
    "PDF invalide {name} : {error}": "Invalid PDF {name}: {error}",
    "PDF généré : {path}": "PDF generated: {path}",
    "Erreur de fusion : {error}": "Merge error: {error}",

    # --- Messages de l'éditeur -------------------------------------------
    "Un seul PDF à la fois : le premier a été ouvert.":
        "One PDF at a time: the first one was opened.",
    "PDF illisible {name} : {error}": "Unreadable PDF {name}: {error}",
    "Chargé : {name}": "Loaded: {name}",
    "Outil : {tool}": "Tool: {tool}",
    "{tool} ajouté(e).": "{tool} added.",
    "Texte ajouté.": "Text added.",
    "Signature ajoutée.": "Signature added.",
    "Dernière annotation retirée.": "Last annotation removed.",
    "Toutes les annotations ont été retirées.": "All annotations were removed.",
    "Rien à enregistrer : ajoutez une annotation ou un filigrane.":
        "Nothing to save: add an annotation or a watermark.",
    "PDF enregistré : {path}": "PDF saved: {path}",
    "Erreur d'enregistrement : {error}": "Save error: {error}",

    # --- Messages des outils PDF ------------------------------------------
    "Un seul PDF à la fois : le premier a été retenu.":
        "One PDF at a time: the first one was kept.",
    "PDF illisible : {error}": "Unreadable PDF: {error}",
    "Chargé : {name} ({pages} pages)": "Loaded: {name} ({pages} pages)",
    "✖ {error}": "✖ {error}",
    "{count} fichier(s) créé(s) dans {folder}": "{count} file(s) created in {folder}",
    "PDF créé : {path}": "PDF created: {path}",
    "PDF protégé (AES-256) : {path}": "PDF protected (AES-256): {path}",
    "PDF déverrouillé : {path}": "PDF unlocked: {path}",
    "déjà optimisé, aucun gain": "already optimised, no gain",

    # --- Onglet Éditeur PDF ---------------------------------------------
    "📂 Ouvrir un PDF": "📂 Open a PDF",
    "Aucun fichier chargé.": "No file loaded.",
    "Outils & propriétés": "Tools & properties",
    "🅰  Texte": "🅰  Text",
    "✍  Signature": "✍  Signature",
    "╱  Ligne": "╱  Line",
    "➜  Flèche": "➜  Arrow",
    "▭  Rectangle": "▭  Rectangle",
    "◯  Ellipse": "◯  Ellipse",
    "▬  Surlignage": "▬  Highlight",
    "██  Caviarder": "██  Redact",
    "── Texte ──": "── Text ──",
    "── Tracé ──": "── Drawing ──",
    "── Filigrane ──": "── Watermark ──",
    "Police": "Font",
    "Taille": "Size",
    "Gras": "Bold",
    "Ital.": "Ital.",
    "Soul.": "Underl.",
    "Couleur": "Colour",
    "Remplissage": "Fill",
    "Épaisseur": "Thickness",
    "Opacité": "Opacity",
    "Intensité": "Intensity",
    "Filigrane sur toutes les pages": "Watermark on every page",
    "💾 Enregistrer sous...": "💾 Save as...",
    "🗑 Tout effacer": "🗑 Clear all",
    "↶ Annuler": "↶ Undo",
    "Ouvrez d'abord un PDF.": "Open a PDF first.",
    "Rien à annuler.": "Nothing to undo.",
    "Aucune annotation à effacer.": "No annotation to clear.",
    "Texte à insérer :": "Text to insert:",
    "Ajouter du texte": "Add text",
    "Glissez la souris pour définir la zone.": "Drag the mouse to define the area.",
    "Aucun": "None",

    # --- Fenêtre Signature ----------------------------------------------
    "Signature": "Signature",
    "Tracez votre signature avec la souris :": "Draw your signature with the mouse:",
    "Encre :": "Ink:",
    "Épaisseur :": "Thickness:",
    "Effacer": "Clear",
    "Importer une image...": "Import an image...",
    "Valider": "Confirm",
    "Choisir une image de signature": "Choose a signature image",

    # --- Onglet Outils PDF ----------------------------------------------
    "📂 Choisir un PDF": "📂 Choose a PDF",
    "Aucun fichier sélectionné  —  ou glissez un PDF ici.":
        "No file selected  —  or drop a PDF here.",
    "Mot de passe du fichier (si protégé) :": "File password (if protected):",
    "laisser vide si non protégé": "leave empty if not protected",
    "✂️  Découper / extraire des pages": "✂️  Split / extract pages",
    "Pages :": "Pages:",
    "ex : 1-3,7   (vide = tout le document)": "e.g. 1-3,7   (empty = whole document)",
    "Un seul fichier avec ces pages": "A single file with these pages",
    "Un fichier par page": "One file per page",
    "Découper": "Split",
    "🗜️  Compresser": "🗜️  Compress",
    "Niveau :": "Level:",
    "Compresser": "Compress",
    "Léger": "Light",
    "Normal": "Normal",
    "Maximum": "Maximum",
    "🔒  Protéger / déverrouiller": "🔒  Protect / unlock",
    "Nouveau mot de passe :": "New password:",
    "mot de passe d'ouverture": "password to open the document",
    "Autoriser l'impression du document": "Allow printing the document",
    "🔒 Protéger": "🔒 Protect",
    "🔓 Déverrouiller": "🔓 Unlock",
    "  (déverrouiller utilise le mot de passe du fichier, en haut)":
        "  (unlocking uses the file password, at the top)",
    "Choisissez d'abord un PDF.": "Choose a PDF first.",
    "Saisissez le nouveau mot de passe.": "Enter the new password.",
    "Saisissez le mot de passe du fichier (champ du haut).":
        "Enter the file password (field at the top).",

    # --- Extraction et numérotation --------------------------------------
    "📤  Extraire le contenu": "📤  Extract content",
    "Texte → .txt": "Text → .txt",
    "Texte → .docx": "Text → .docx",
    "Images embarquées": "Embedded images",
    "🔢  Numéroter / en-tête / pied de page": "🔢  Numbering / header / footer",
    "Position :": "Position:",
    "Format :": "Format:",
    "Commencer à :": "Start at:",
    "Ne pas numéroter la première page (couverture)":
        "Do not number the first page (cover)",
    "En-tête :": "Header:",
    "Pied de page :": "Footer:",
    "laisser vide pour aucun": "leave empty for none",
    "Appliquer": "Apply",
    "Bas centre": "Bottom centre",
    "Bas droite": "Bottom right",
    "Bas gauche": "Bottom left",
    "Haut centre": "Top centre",
    "Haut droite": "Top right",
    "Haut gauche": "Top left",
    "Le numéro de départ doit être un nombre entier.":
        "The starting number must be a whole number.",
    "PDF numéroté : {path}": "PDF numbered: {path}",
    "{count} caractères extraits : {path}": "{count} characters extracted: {path}",
    "Aucun texte trouvé : ce PDF est probablement un scan. Fichier créé mais vide : {path}":
        "No text found: this PDF is probably a scan. File created but empty: {path}",
    "{count} image(s) extraite(s) dans {folder}": "{count} image(s) extracted into {folder}",
    "Aucune image embarquée dans ce PDF.": "No embedded image in this PDF.",

    # --- Onglet Organiser -------------------------------------------------
    "🗂️ Organiser": "🗂️ Organise",
    "Pages  —  cliquez pour sélectionner": "Pages  —  click to select",
    "◀ Reculer": "◀ Move back",
    "Avancer ▶": "Move forward ▶",
    "↺ Pivoter": "↺ Rotate",
    "↻ Pivoter": "↻ Rotate",
    "🗑 Supprimer": "🗑 Delete",
    "↩ Réinitialiser": "↩ Reset",
    "Sélectionnez d'abord une page.": "Select a page first.",
    "Le document doit conserver au moins une page.":
        "The document must keep at least one page.",
    "PDF réorganisé : {path}": "PDF reorganised: {path}",

    # --- Couleurs partagées ---------------------------------------------
    "Noir": "Black",
    "Rouge": "Red",
    "Bleu": "Blue",
    "Vert": "Green",
    "Orange": "Orange",
    "Jaune": "Yellow",
    "Blanc": "White",
    "Gris": "Grey",
}


def set_language(language: str) -> None:
    """Fixe la langue de l'interface ; une valeur inconnue retombe sur le français."""
    global _current
    _current = language if language in LANGUAGES else "fr"


def get_language() -> str:
    """Langue actuellement active."""
    return _current


def t(text: str) -> str:
    """Traduit une chaîne de l'interface.

    Retourne le texte français d'origine si la langue active est le français,
    ou si aucune traduction n'existe pour cette chaîne.
    """
    if _current == "fr":
        return text
    return TRANSLATIONS.get(text, text)


def tl(texts) -> list[str]:
    """Traduit une suite de chaînes, pour peupler un menu déroulant."""
    return [t(item) for item in texts]


def untranslate(text: str) -> str:
    """Retrouve la clé française à partir du libellé affiché.

    Plusieurs menus utilisent les libellés français comme clés de
    dictionnaire (couleurs, niveaux de compression, langues de sous-titres).
    Une fois l'affichage traduit, la valeur lue dans le menu doit être
    reconvertie avant toute recherche, sans quoi la sélection ne
    correspondrait plus à aucune entrée.
    """
    if _current == "fr":
        return text
    for french, english in TRANSLATIONS.items():
        if english == text:
            return french
    return text
