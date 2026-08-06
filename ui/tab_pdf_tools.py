"""Onglet Outils PDF : découper, compresser, protéger ou déverrouiller.

Contrairement à l'onglet Fusion (plusieurs fichiers en entrée) et à l'onglet
Éditeur (annotation page par page), toutes les opérations d'ici portent sur un
seul document : un unique sélecteur de fichier est donc partagé par les trois
sections, plutôt que répété trois fois.
"""

import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core.pdf_tools import (
    COMPRESSION_LEVELS,
    NUMBER_FORMATS,
    NUMBER_POSITIONS,
    add_page_numbers,
    compress_pdf,
    extract_images,
    extract_text,
    page_count,
    protect_pdf,
    split_pdf,
    unlock_pdf,
)
from ui.dnd import register_drop_target
from ui.widgets import LogBox, bind_memory
from utils.helpers import human_size
from utils.i18n import t, tl, untranslate
from utils.security import SecurityError


class PdfToolsTab(ctk.CTkFrame):
    """UI des opérations sur un document PDF entier."""

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.source: str | None = None
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self)
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(top, text=t("📂 Choisir un PDF"), command=self._pick_source)\
            .grid(row=0, column=0, padx=8, pady=8)
        self.source_label = ctk.CTkLabel(
            top, text=t("Aucun fichier sélectionné  —  ou glissez un PDF ici."), anchor="w")
        self.source_label.grid(row=0, column=1, sticky="ew", padx=8)
        register_drop_target(top, self._on_drop)

        ctk.CTkLabel(top, text=t("Mot de passe du fichier (si protégé) :"), anchor="w")\
            .grid(row=1, column=0, padx=8, pady=(0, 8), sticky="w")
        self.source_password = ctk.CTkEntry(top, show="•", placeholder_text=t("laisser vide si non protégé"))
        self.source_password.grid(row=1, column=1, sticky="ew", padx=8, pady=(0, 8))

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        body.grid_columnconfigure(0, weight=1)
        self._build_split(body)
        self._build_extract(body)
        self._build_numbering(body)
        self._build_compress(body)
        self._build_protect(body)

        self.logbox = LogBox(self)
        self.logbox.grid(row=2, column=0, sticky="ew", padx=10, pady=(5, 10))

    @staticmethod
    def _section(parent, title: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=6)
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame, text=t(title), anchor="w",
                     font=ctk.CTkFont(size=14, weight="bold"))\
            .grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(8, 4))
        return frame

    def _build_split(self, parent) -> None:
        frame = self._section(parent, "✂️  Découper / extraire des pages")

        ctk.CTkLabel(frame, text=t("Pages :"), anchor="w").grid(row=1, column=0, padx=10, pady=6, sticky="w")
        self.split_range = ctk.CTkEntry(frame, placeholder_text=t("ex : 1-3,7   (vide = tout le document)"))
        self.split_range.grid(row=1, column=1, columnspan=2, sticky="ew", padx=10, pady=6)

        self.split_mode = ctk.StringVar(value="single")
        modes = ctk.CTkFrame(frame, fg_color="transparent")
        modes.grid(row=2, column=0, columnspan=3, sticky="w", padx=10)
        ctk.CTkRadioButton(modes, text=t("Un seul fichier avec ces pages"),
                           variable=self.split_mode, value="single").pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(modes, text=t("Un fichier par page"),
                           variable=self.split_mode, value="per_page").pack(side="left")

        ctk.CTkButton(frame, text=t("Découper"), command=self._split)\
            .grid(row=3, column=0, padx=10, pady=10, sticky="w")

    def _build_extract(self, parent) -> None:
        frame = self._section(parent, "📤  Extraire le contenu")

        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.grid(row=1, column=0, columnspan=3, sticky="w", padx=10, pady=10)
        ctk.CTkButton(actions, text=t("Texte → .txt"), width=130,
                      command=lambda: self._extract_text(".txt")).pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text=t("Texte → .docx"), width=130,
                      command=lambda: self._extract_text(".docx")).pack(side="left", padx=8)
        ctk.CTkButton(actions, text=t("Images embarquées"), width=160,
                      command=self._extract_images).pack(side="left", padx=8)

    def _build_numbering(self, parent) -> None:
        frame = self._section(parent, "🔢  Numéroter / en-tête / pied de page")

        ctk.CTkLabel(frame, text=t("Position :"), anchor="w")\
            .grid(row=1, column=0, padx=10, pady=6, sticky="w")
        self.number_position = ctk.CTkOptionMenu(frame, values=tl(NUMBER_POSITIONS), width=150)
        self.number_position.set(t("Bas centre"))
        self.number_position.grid(row=1, column=1, sticky="w", padx=10, pady=6)

        ctk.CTkLabel(frame, text=t("Format :"), anchor="w")\
            .grid(row=2, column=0, padx=10, pady=6, sticky="w")
        self.number_format = ctk.CTkOptionMenu(frame, values=list(NUMBER_FORMATS), width=180)
        self.number_format.set("{n}")
        self.number_format.grid(row=2, column=1, sticky="w", padx=10, pady=6)

        ctk.CTkLabel(frame, text=t("Commencer à :"), anchor="w")\
            .grid(row=3, column=0, padx=10, pady=6, sticky="w")
        self.number_start = ctk.CTkEntry(frame, width=80, placeholder_text="1")
        self.number_start.grid(row=3, column=1, sticky="w", padx=10, pady=6)

        self.skip_first = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(frame, text=t("Ne pas numéroter la première page (couverture)"),
                        variable=self.skip_first)\
            .grid(row=4, column=0, columnspan=3, sticky="w", padx=10, pady=4)

        ctk.CTkLabel(frame, text=t("En-tête :"), anchor="w")\
            .grid(row=5, column=0, padx=10, pady=6, sticky="w")
        self.header_entry = ctk.CTkEntry(frame, placeholder_text=t("laisser vide pour aucun"))
        self.header_entry.grid(row=5, column=1, columnspan=2, sticky="ew", padx=10, pady=6)

        ctk.CTkLabel(frame, text=t("Pied de page :"), anchor="w")\
            .grid(row=6, column=0, padx=10, pady=6, sticky="w")
        self.footer_entry = ctk.CTkEntry(frame, placeholder_text=t("laisser vide pour aucun"))
        self.footer_entry.grid(row=6, column=1, columnspan=2, sticky="ew", padx=10, pady=6)

        ctk.CTkButton(frame, text=t("Appliquer"), command=self._add_numbers)\
            .grid(row=7, column=0, padx=10, pady=10, sticky="w")

    def _build_compress(self, parent) -> None:
        frame = self._section(parent, "🗜️  Compresser")

        ctk.CTkLabel(frame, text=t("Niveau :"), anchor="w").grid(row=1, column=0, padx=10, pady=6, sticky="w")
        self.compress_level = ctk.CTkOptionMenu(frame, values=tl(COMPRESSION_LEVELS), width=140)
        self.compress_level.set(t("Normal"))
        self.compress_level.grid(row=1, column=1, sticky="w", padx=10, pady=6)

        bind_memory(self.app, self.compress_level, "pdf.compression")
        ctk.CTkButton(frame, text=t("Compresser"), command=self._compress)\
            .grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.compress_result = ctk.CTkLabel(frame, text="", anchor="w")
        self.compress_result.grid(row=2, column=1, columnspan=2, sticky="w", padx=10)

    def _build_protect(self, parent) -> None:
        frame = self._section(parent, "🔒  Protéger / déverrouiller")

        ctk.CTkLabel(frame, text=t("Nouveau mot de passe :"), anchor="w")\
            .grid(row=1, column=0, padx=10, pady=6, sticky="w")
        self.new_password = ctk.CTkEntry(frame, show="•", placeholder_text=t("mot de passe d'ouverture"))
        self.new_password.grid(row=1, column=1, columnspan=2, sticky="ew", padx=10, pady=6)

        self.allow_printing = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(frame, text=t("Autoriser l'impression du document"),
                        variable=self.allow_printing)\
            .grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=4)

        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=10)
        ctk.CTkButton(actions, text=t("🔒 Protéger"), command=self._protect).pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text=t("🔓 Déverrouiller"), fg_color="#555",
                      command=self._unlock).pack(side="left")
        ctk.CTkLabel(actions, text=t("  (déverrouiller utilise le mot de passe du fichier, en haut)"),
                     anchor="w").pack(side="left", padx=8)

    # --------------------------------------------------------------- source
    def _on_drop(self, paths) -> None:
        """Prend le premier PDF déposé : ces opérations portent sur un seul document."""
        if not paths:
            return
        if len(paths) > 1:
            self.logbox.log(t("Un seul PDF à la fois : le premier a été retenu."))
        self._load_source(paths[0])

    def _pick_source(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        self._load_source(path)

    def _load_source(self, path: str) -> None:
        """Retient un PDF comme source et affiche son nombre de pages."""
        self.source = path
        self.source_label.configure(text=Path(path).name)
        try:
            pages = page_count(path, self.source_password.get())
        except SecurityError as e:
            self.logbox.log(t("⛔ {name} refusé (sécurité) : {error}").format(
                name=Path(path).name, error=e), "error")
            return
        except ValueError as e:
            # Document protégé : on garde le fichier sélectionné, l'utilisateur
            # peut saisir le mot de passe puis relancer l'opération voulue.
            self.logbox.log(f"🔒 {e}", "error")
            return
        except Exception as e:
            self.logbox.log(t("PDF illisible : {error}").format(error=e), "error")
            return
        self.source_label.configure(text=f"{Path(path).name} — {pages} page(s)")
        self.logbox.log(t("Chargé : {name} ({pages} pages)").format(
            name=Path(path).name, pages=pages), "success")

    def _require_source(self) -> bool:
        if not self.source:
            self.logbox.log(t("Choisissez d'abord un PDF."), "error")
            return False
        return True

    def _run(self, action, success_message) -> None:
        """Exécute une opération en tâche de fond et journalise le résultat."""

        def worker() -> None:
            try:
                result = action()
            except SecurityError as e:
                self.logbox.log(t("⛔ Sécurité : {error}").format(error=e), "error")
            except ValueError as e:
                self.logbox.log(t("✖ {error}").format(error=e), "error")
            except Exception as e:
                self.logbox.log(t("Erreur : {error}").format(error=e), "error")
            else:
                self.logbox.log(success_message(result), "success")

        threading.Thread(target=worker, daemon=True).start()

    # -------------------------------------------------------------- actions
    def _split(self) -> None:
        if not self._require_source():
            return
        folder = filedialog.askdirectory(initialdir=self.app.config_data["output_dir"])
        if not folder:
            return
        source, password = self.source, self.source_password.get()
        ranges = self.split_range.get().strip()
        per_page = self.split_mode.get() == "per_page"

        self._run(
            lambda: split_pdf(source, folder, ranges, per_page, password),
            lambda created: (t("{count} fichier(s) créé(s) dans {folder}").format(
                                 count=len(created), folder=folder)
                             if len(created) > 1
                             else t("PDF créé : {path}").format(path=created[0])),
        )

    def _extract_text(self, suffix: str) -> None:
        if not self._require_source():
            return
        output = filedialog.asksaveasfilename(
            defaultextension=suffix,
            filetypes=[("Texte", "*.txt")] if suffix == ".txt" else [("Word", "*.docx")])
        if not output:
            return
        source, password = self.source, self.source_password.get()

        def describe(result) -> str:
            path, length = result
            if length == 0:
                # Un PDF scanné n'a aucune couche de texte : livrer un fichier
                # vide sans rien dire laisserait croire à un dysfonctionnement.
                return t("Aucun texte trouvé : ce PDF est probablement un scan. "
                         "Fichier créé mais vide : {path}").format(path=path)
            return t("{count} caractères extraits : {path}").format(
                count=length, path=path)

        self._run(lambda: extract_text(source, output, password), describe)

    def _extract_images(self) -> None:
        if not self._require_source():
            return
        folder = filedialog.askdirectory(initialdir=self.app.config_data["output_dir"])
        if not folder:
            return
        source, password = self.source, self.source_password.get()

        self._run(
            lambda: extract_images(source, folder, password),
            lambda created: (t("{count} image(s) extraite(s) dans {folder}").format(
                                 count=len(created), folder=folder)
                             if created
                             else t("Aucune image embarquée dans ce PDF.")),
        )

    def _add_numbers(self) -> None:
        if not self._require_source():
            return
        raw_start = self.number_start.get().strip() or "1"
        if not raw_start.isdigit():
            self.logbox.log(t("Le numéro de départ doit être un nombre entier."), "error")
            return
        output = filedialog.asksaveasfilename(defaultextension=".pdf",
                                              filetypes=[("PDF", "*.pdf")])
        if not output:
            return

        source, password = self.source, self.source_password.get()
        position = untranslate(self.number_position.get())
        number_format = self.number_format.get()
        start_at = int(raw_start)
        skip_first = self.skip_first.get()
        header, footer = self.header_entry.get().strip(), self.footer_entry.get().strip()

        self._run(
            lambda: add_page_numbers(source, output, position, number_format,
                                     start_at, skip_first, header=header,
                                     footer=footer, password=password),
            lambda path: t("PDF numéroté : {path}").format(path=path),
        )

    def _compress(self) -> None:
        if not self._require_source():
            return
        output = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not output:
            return
        source, password = self.source, self.source_password.get()
        # Le menu affiche le niveau traduit : on repasse par la clé française.
        level = untranslate(self.compress_level.get())

        def describe(result) -> str:
            path, before, after = result
            self.after(0, lambda: self.compress_result.configure(text=self._ratio(before, after)))
            return f"{self._ratio(before, after)} → {path}"

        self._run(lambda: compress_pdf(source, output, level, password), describe)

    @staticmethod
    def _ratio(before: int, after: int) -> str:
        """Formule le gain, ou son absence — un PDF déjà optimisé peut grossir."""
        if after >= before:
            return (f"{human_size(before)} → {human_size(after)} "
                    f"({t('déjà optimisé, aucun gain')})")
        gain = (1 - after / before) * 100
        return f"{human_size(before)} → {human_size(after)} (−{gain:.0f} %)"

    def _protect(self) -> None:
        if not self._require_source():
            return
        password = self.new_password.get()
        if not password:
            self.logbox.log(t("Saisissez le nouveau mot de passe."), "error")
            return
        output = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not output:
            return
        source, current = self.source, self.source_password.get()
        printing = self.allow_printing.get()

        self._run(
            lambda: protect_pdf(source, output, password, printing, current),
            lambda path: t("PDF protégé (AES-256) : {path}").format(path=path),
        )

    def _unlock(self) -> None:
        if not self._require_source():
            return
        password = self.source_password.get()
        if not password:
            self.logbox.log(t("Saisissez le mot de passe du fichier (champ du haut)."), "error")
            return
        output = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if not output:
            return
        source = self.source

        self._run(
            lambda: unlock_pdf(source, output, password),
            lambda path: t("PDF déverrouillé : {path}").format(path=path),
        )
