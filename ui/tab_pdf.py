"""Onglet PDF : assemblage, plages de pages, rotation, réorganisation."""

import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core.pdf_merger import PdfItem, merge_pdfs
from ui.widgets import LogBox
from utils.helpers import open_in_explorer


class PdfTab(ctk.CTkFrame):
    """UI d'assemblage PDF : liste réorderable, plages, rotation, fusion."""

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.items: list[PdfItem] = []
        self.last_output: str | None = None
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        ctk.CTkButton(top, text="➕ Ajouter des PDF", command=self._add_pdfs).pack(side="left", padx=5)

        self.grid_rowconfigure(1, weight=1)
        self.list_frame = ctk.CTkScrollableFrame(self, label_text="PDF à fusionner (ordre = ordre de fusion)")
        self.list_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        out = ctk.CTkFrame(self)
        out.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        out.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(out, text="Sortie :").grid(row=0, column=0, padx=8, pady=8)
        self.out_entry = ctk.CTkEntry(out)
        self.out_entry.insert(0, str(Path(self.app.config_data["output_dir"]) / "fusion.pdf"))
        self.out_entry.grid(row=0, column=1, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(out, text="Parcourir...", width=100, command=self._browse_out)\
            .grid(row=0, column=2, padx=8, pady=8)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        self.merge_btn = ctk.CTkButton(actions, text="Fusionner", command=self._merge)
        self.merge_btn.pack(side="left", padx=5)
        self.open_btn = ctk.CTkButton(actions, text="Ouvrir le fichier généré",
                                      state="disabled", fg_color="#2e7d32", command=self._open_result)
        self.open_btn.pack(side="left", padx=5)

        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.grid(row=4, column=0, sticky="ew", padx=10, pady=5)

        self.logbox = LogBox(self)
        self.logbox.grid(row=5, column=0, sticky="ew", padx=10, pady=(5, 10))

    def _render_list(self) -> None:
        """Reconstruit la liste des PDF avec contrôles ↑ ↓, plage, rotation, ✖."""
        for w in self.list_frame.winfo_children():
            w.destroy()
        for i, item in enumerate(self.items):
            row = ctk.CTkFrame(self.list_frame)
            row.pack(fill="x", pady=3, padx=2)
            row.grid_columnconfigure(2, weight=1)

            ctk.CTkButton(row, text="↑", width=28, command=lambda i=i: self._move(i, -1))\
                .grid(row=0, column=0, padx=(4, 0), pady=4)
            ctk.CTkButton(row, text="↓", width=28, command=lambda i=i: self._move(i, 1))\
                .grid(row=0, column=1, padx=2, pady=4)
            ctk.CTkLabel(row, text=f"{item.name}  ({item.num_pages} pages)", anchor="w")\
                .grid(row=0, column=2, sticky="ew", padx=6)

            range_entry = ctk.CTkEntry(row, width=110, placeholder_text="Pages ex: 1-3,5")
            range_entry.insert(0, item.page_range)
            range_entry.grid(row=0, column=3, padx=4)
            range_entry.bind("<FocusOut>",
                             lambda e, it=item, en=range_entry: setattr(it, "page_range", en.get()))

            rot_menu = ctk.CTkOptionMenu(row, width=80, values=["0°", "90°", "180°", "270°"],
                                         command=lambda v, it=item: setattr(it, "rotation", int(v.rstrip("°"))))
            rot_menu.set(f"{item.rotation}°")
            rot_menu.grid(row=0, column=4, padx=4)

            ctk.CTkButton(row, text="✖", width=28, fg_color="#8a3333",
                          command=lambda i=i: self._remove(i)).grid(row=0, column=5, padx=4)

    # ------------------------------------------------------------- handlers
    def _add_pdfs(self) -> None:
        paths = filedialog.askopenfilenames(filetypes=[("PDF", "*.pdf")])
        for p in paths:
            try:
                item = PdfItem(p)
                _ = item.num_pages  # valide le fichier
                self.items.append(item)
            except Exception as e:
                self.logbox.log(f"PDF invalide {Path(p).name} : {e}", "error")
        self._render_list()

    def _move(self, index: int, delta: int) -> None:
        j = index + delta
        if 0 <= j < len(self.items):
            self.items[index], self.items[j] = self.items[j], self.items[index]
            self._render_list()

    def _remove(self, index: int) -> None:
        self.items.pop(index)
        self._render_list()

    def _browse_out(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")])
        if path:
            self.out_entry.delete(0, "end")
            self.out_entry.insert(0, path)

    def _merge(self) -> None:
        if not self.items:
            self.logbox.log("Ajoutez au moins un PDF.", "error")
            return
        output = self.out_entry.get().strip()
        self.merge_btn.configure(state="disabled")
        self.progress.set(0)
        items = list(self.items)

        def cb(frac: float, msg: str) -> None:
            self.after(0, lambda: self.progress.set(frac))
            self.logbox.log(msg)

        def worker() -> None:
            try:
                self.last_output = merge_pdfs(items, output, cb)
                self.logbox.log(f"PDF généré : {self.last_output}", "success")
                self.after(0, lambda: self.open_btn.configure(state="normal"))
            except Exception as e:
                self.logbox.log(f"Erreur de fusion : {e}", "error")
            finally:
                self.after(0, lambda: self.merge_btn.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()

    def _open_result(self) -> None:
        if self.last_output:
            open_in_explorer(self.last_output)
