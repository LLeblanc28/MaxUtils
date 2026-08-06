"""Onglet Organiser : réordonner, supprimer et pivoter les pages d'un PDF.

Là où l'onglet Fusion assemble plusieurs documents et où Outils PDF découpe,
celui-ci réorganise l'intérieur d'un document unique. Les pages sont
présentées en vignettes, l'ordre affiché étant celui du fichier produit.
"""

import io
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core.pdf_tools import organize_pages, page_count, render_thumbnail
from ui.dnd import register_drop_target
from ui.widgets import LogBox
from utils.i18n import t
from utils.security import SecurityError

THUMB_WIDTH = 130
COLUMNS = 5


class PdfOrganizerTab(ctk.CTkFrame):
    """UI de réorganisation des pages d'un PDF."""

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.source: str | None = None
        # (index d'origine, rotation) : l'ordre de cette liste est l'ordre du
        # document final, et une page retirée en disparaît simplement.
        self.pages: list[list[int]] = []
        self.selected: int | None = None
        self._thumbnails: dict[int, object] = {}
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        ctk.CTkButton(top, text=t("📂 Choisir un PDF"), command=self._pick_source)\
            .pack(side="left", padx=5)
        self.source_label = ctk.CTkLabel(
            top, text=t("Aucun fichier sélectionné  —  ou glissez un PDF ici."), anchor="w")
        self.source_label.pack(side="left", padx=10)
        register_drop_target(top, self._on_drop)

        self.grid_frame = ctk.CTkScrollableFrame(
            self, label_text=t("Pages  —  cliquez pour sélectionner"))
        self.grid_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        actions = ctk.CTkFrame(self)
        actions.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        ctk.CTkButton(actions, text=t("◀ Reculer"), width=100,
                      command=lambda: self._move(-1)).pack(side="left", padx=(10, 4), pady=8)
        ctk.CTkButton(actions, text=t("Avancer ▶"), width=100,
                      command=lambda: self._move(1)).pack(side="left", padx=4, pady=8)
        ctk.CTkButton(actions, text=t("↺ Pivoter"), width=100,
                      command=lambda: self._rotate(-90)).pack(side="left", padx=(16, 4), pady=8)
        ctk.CTkButton(actions, text=t("↻ Pivoter"), width=100,
                      command=lambda: self._rotate(90)).pack(side="left", padx=4, pady=8)
        ctk.CTkButton(actions, text=t("🗑 Supprimer"), width=110, fg_color="#8a3333",
                      command=self._delete).pack(side="left", padx=(16, 4), pady=8)
        ctk.CTkButton(actions, text=t("↩ Réinitialiser"), width=120, fg_color="#555",
                      command=self._reset).pack(side="left", padx=4, pady=8)
        ctk.CTkButton(actions, text=t("💾 Enregistrer sous..."),
                      command=self._save).pack(side="right", padx=10, pady=8)

        self.logbox = LogBox(self)
        self.logbox.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 10))

    # --------------------------------------------------------------- source
    def _on_drop(self, paths) -> None:
        """Prend le premier PDF déposé : l'organisation porte sur un document."""
        if not paths:
            return
        if len(paths) > 1:
            self.logbox.log(t("Un seul PDF à la fois : le premier a été retenu."))
        self._load(paths[0])

    def _pick_source(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if path:
            self._load(path)

    def _load(self, path: str) -> None:
        """Charge un PDF et construit la grille de vignettes."""
        try:
            total = page_count(path)
        except SecurityError as e:
            self.logbox.log(t("⛔ {name} refusé (sécurité) : {error}").format(
                name=Path(path).name, error=e), "error")
            return
        except ValueError as e:
            self.logbox.log(f"🔒 {e}", "error")
            return
        except Exception as e:
            self.logbox.log(t("PDF illisible : {error}").format(error=e), "error")
            return

        self.source = path
        self.pages = [[i, 0] for i in range(total)]
        self.selected = None
        self._thumbnails = {}
        self.source_label.configure(
            text=t("Chargé : {name} ({pages} pages)").format(
                name=Path(path).name, pages=total))
        self.logbox.log(t("Chargé : {name} ({pages} pages)").format(
            name=Path(path).name, pages=total), "success")
        self._render()

    # ---------------------------------------------------------------- grille
    def _thumbnail(self, index: int):
        """Vignette d'une page d'origine, rendue une seule fois puis conservée.

        Un CTkImage plutôt qu'un PhotoImage : lui seul est remis à l'échelle
        sur les écrans à forte densité, où les vignettes seraient sinon floues.
        """
        from PIL import Image

        if index not in self._thumbnails:
            png = render_thumbnail(self.source, index, THUMB_WIDTH)
            image = Image.open(io.BytesIO(png))
            self._thumbnails[index] = ctk.CTkImage(
                light_image=image, dark_image=image, size=image.size)
        return self._thumbnails[index]

    def _render(self) -> None:
        """Reconstruit la grille : une tuile par page conservée, dans l'ordre."""
        for widget in self.grid_frame.winfo_children():
            widget.destroy()
        if not self.source:
            return

        for position, (origin, rotation) in enumerate(self.pages):
            selected = position == self.selected
            tile = ctk.CTkFrame(self.grid_frame,
                                border_width=3 if selected else 1,
                                border_color="#4d9bff" if selected else "#555")
            tile.grid(row=position // COLUMNS, column=position % COLUMNS, padx=6, pady=6)

            label = ctk.CTkLabel(tile, image=self._thumbnail(origin), text="")
            label.pack(padx=4, pady=(4, 0))
            caption = f"{position + 1}"
            if rotation:
                caption += f"   {rotation}°"
            ctk.CTkLabel(tile, text=caption).pack(pady=(0, 4))

            # Le clic est capté sur la tuile et sur ses enfants : sans cela,
            # cliquer sur la vignette elle-même ne sélectionnerait rien.
            for widget in (tile, label):
                widget.bind("<Button-1>", lambda _e, p=position: self._select(p))

    def _select(self, position: int) -> None:
        self.selected = position
        self._render()

    def _require_selection(self) -> bool:
        if self.selected is None:
            self.logbox.log(t("Sélectionnez d'abord une page."), "error")
            return False
        return True

    # -------------------------------------------------------------- actions
    def _move(self, delta: int) -> None:
        if not self._require_selection():
            return
        target = self.selected + delta
        if not 0 <= target < len(self.pages):
            return
        self.pages[self.selected], self.pages[target] = (
            self.pages[target], self.pages[self.selected])
        self.selected = target
        self._render()

    def _rotate(self, degrees: int) -> None:
        if not self._require_selection():
            return
        self.pages[self.selected][1] = (self.pages[self.selected][1] + degrees) % 360
        self._render()

    def _delete(self) -> None:
        if not self._require_selection():
            return
        if len(self.pages) == 1:
            self.logbox.log(t("Le document doit conserver au moins une page."), "error")
            return
        self.pages.pop(self.selected)
        self.selected = None
        self._render()

    def _reset(self) -> None:
        """Revient à l'ordre et aux orientations d'origine."""
        if not self.source:
            self.logbox.log(t("Choisissez d'abord un PDF."), "error")
            return
        self._load(self.source)

    def _save(self) -> None:
        if not self.source:
            self.logbox.log(t("Choisissez d'abord un PDF."), "error")
            return
        output = filedialog.asksaveasfilename(defaultextension=".pdf",
                                              filetypes=[("PDF", "*.pdf")])
        if not output:
            return
        source = self.source
        pages = [(origin, rotation) for origin, rotation in self.pages]

        def worker() -> None:
            try:
                path = organize_pages(source, output, pages)
            except SecurityError as e:
                self.logbox.log(t("⛔ Sécurité : {error}").format(error=e), "error")
            except ValueError as e:
                self.logbox.log(t("✖ {error}").format(error=e), "error")
            except Exception as e:
                self.logbox.log(t("Erreur : {error}").format(error=e), "error")
            else:
                self.logbox.log(t("PDF réorganisé : {path}").format(path=path), "success")

        threading.Thread(target=worker, daemon=True).start()
