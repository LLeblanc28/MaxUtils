"""Onglet Convertisseur : conversion multi-fichiers entre formats."""

import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core.file_converter import convert_file, detect_category
from ui.widgets import LogBox
from utils.config import TARGETS_BY_CATEGORY
from utils.security import SecurityError


class ConverterTab(ctk.CTkFrame):
    """UI de conversion de fichiers : sélection multiple, format cible, batch."""

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.files: list[str] = []
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        ctk.CTkButton(top, text="➕ Ajouter des fichiers", command=self._add_files).pack(side="left", padx=5)
        ctk.CTkButton(top, text="🗑 Vider la liste", fg_color="#555",
                      command=self._clear).pack(side="left", padx=5)

        self.grid_rowconfigure(1, weight=1)
        self.file_list = ctk.CTkScrollableFrame(self, label_text="Fichiers à convertir")
        self.file_list.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        opts = ctk.CTkFrame(self)
        opts.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        opts.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(opts, text="Format cible :").grid(row=0, column=0, padx=8, pady=8)
        self.target_menu = ctk.CTkOptionMenu(opts, values=["—"])
        self.target_menu.grid(row=0, column=1, padx=8, pady=8)
        self.dest_entry = ctk.CTkEntry(opts)
        self.dest_entry.insert(0, self.app.config_data["output_dir"])
        self.dest_entry.grid(row=0, column=2, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(opts, text="Parcourir...", width=100, command=self._browse)\
            .grid(row=0, column=3, padx=8, pady=8)

        self.convert_btn = ctk.CTkButton(self, text="Convertir tout", command=self._convert_all)
        self.convert_btn.grid(row=3, column=0, padx=10, pady=5, sticky="w")

        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.grid(row=4, column=0, sticky="ew", padx=10, pady=5)

        self.logbox = LogBox(self)
        self.logbox.grid(row=5, column=0, sticky="ew", padx=10, pady=(5, 10))

    # ------------------------------------------------------------- handlers
    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames()
        for p in paths:
            if p in self.files:
                continue
            cat = detect_category(p)
            if cat is None:
                self.logbox.log(f"Format non supporté : {Path(p).name}", "error")
                continue
            self.files.append(p)
            row = ctk.CTkFrame(self.file_list, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=f"{Path(p).name}  [{cat}]", anchor="w").pack(side="left", padx=5)
        self._refresh_targets()

    def _clear(self) -> None:
        self.files.clear()
        for w in self.file_list.winfo_children():
            w.destroy()
        self.target_menu.configure(values=["—"])
        self.target_menu.set("—")

    def _refresh_targets(self) -> None:
        """Propose l'union des formats cibles des catégories présentes."""
        cats = {detect_category(f) for f in self.files if detect_category(f)}
        targets: list[str] = []
        for c in cats:
            targets += [t for t in TARGETS_BY_CATEGORY[c] if t not in targets]
        if targets:
            self.target_menu.configure(values=targets)
            self.target_menu.set(targets[0])

    def _browse(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.dest_entry.get())
        if folder:
            self.dest_entry.delete(0, "end")
            self.dest_entry.insert(0, folder)

    def _convert_all(self) -> None:
        if not self.files:
            self.logbox.log("Aucun fichier à convertir.", "error")
            return
        target = self.target_menu.get()
        if target == "—":
            self.logbox.log("Choisissez un format cible.", "error")
            return
        dest = self.dest_entry.get().strip()
        self.convert_btn.configure(state="disabled")
        files = list(self.files)

        def worker() -> None:
            total = len(files)
            for i, f in enumerate(files):
                try:
                    out = convert_file(f, target, dest)
                    self.logbox.log(f"✔ {Path(f).name} → {Path(out).name}", "success")
                except SecurityError as e:
                    self.logbox.log(f"⛔ {Path(f).name} refusé (sécurité) : {e}", "error")
                except Exception as e:
                    self.logbox.log(f"✖ {Path(f).name} : {e}", "error")
                self.after(0, lambda v=(i + 1) / total: self.progress.set(v))
            self.logbox.log("Conversion terminée.", "success")
            self.after(0, lambda: self.convert_btn.configure(state="normal"))

        threading.Thread(target=worker, daemon=True).start()
