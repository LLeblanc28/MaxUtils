"""Fenêtre principale : onglets Vidéo / Convertisseur / PDF + paramètres."""

import os
from tkinter import filedialog

import customtkinter as ctk

from ui.tab_converter import ConverterTab
from ui.tab_pdf import PdfTab
from ui.tab_video import VideoTab
from utils.config import (
    APP_NAME,
    APP_VERSION,
    MIN_WINDOW_SIZE,
    load_config,
    resource_path,
    save_config,
)


class MultiToolApp(ctk.CTk):
    """Fenêtre principale de l'application."""

    def __init__(self) -> None:
        super().__init__()
        self.config_data = load_config()

        ctk.set_appearance_mode(self.config_data["theme"])
        ctk.set_default_color_theme("blue")

        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry("900x650")
        self.minsize(*MIN_WINDOW_SIZE)
        icon = resource_path(os.path.join("assets", "icon.ico"))
        if os.path.isfile(icon):
            try:
                self.iconbitmap(icon)
            except Exception:
                pass  # icône non critique (Linux/Mac)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Barre du haut : titre + bouton paramètres
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text="🛠️ Multi-Outils", font=ctk.CTkFont(size=18, weight="bold"))\
            .grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="⚙️", width=40, command=self._open_settings)\
            .grid(row=0, column=1, sticky="e")

        # Onglets
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        for name in ("📥 Vidéo", "🔄 Convertisseur", "📄 PDF"):
            self.tabview.add(name)

        VideoTab(self.tabview.tab("📥 Vidéo"), self).pack(fill="both", expand=True)
        ConverterTab(self.tabview.tab("🔄 Convertisseur"), self).pack(fill="both", expand=True)
        PdfTab(self.tabview.tab("📄 PDF"), self).pack(fill="both", expand=True)

    # -------------------------------------------------------------- settings
    def _open_settings(self) -> None:
        """Ouvre la fenêtre de paramètres (thème, dossier, langue)."""
        win = ctk.CTkToplevel(self)
        win.title("Paramètres")
        win.geometry("420x260")
        win.grab_set()
        win.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(win, text="Thème :").grid(row=0, column=0, padx=12, pady=12, sticky="w")
        theme_menu = ctk.CTkOptionMenu(win, values=["dark", "light"],
                                       command=self._change_theme)
        theme_menu.set(self.config_data["theme"])
        theme_menu.grid(row=0, column=1, padx=12, pady=12, sticky="ew")

        ctk.CTkLabel(win, text="Langue :").grid(row=1, column=0, padx=12, pady=12, sticky="w")
        lang_menu = ctk.CTkOptionMenu(win, values=["fr", "en"],
                                      command=lambda v: self._set_cfg("language", v))
        lang_menu.set(self.config_data["language"])
        lang_menu.grid(row=1, column=1, padx=12, pady=12, sticky="ew")

        ctk.CTkLabel(win, text="Dossier de sortie :").grid(row=2, column=0, padx=12, pady=12, sticky="w")
        out_entry = ctk.CTkEntry(win)
        out_entry.insert(0, self.config_data["output_dir"])
        out_entry.grid(row=2, column=1, padx=12, pady=12, sticky="ew")

        def browse() -> None:
            folder = filedialog.askdirectory(initialdir=out_entry.get())
            if folder:
                out_entry.delete(0, "end")
                out_entry.insert(0, folder)
                self._set_cfg("output_dir", folder)

        ctk.CTkButton(win, text="Parcourir...", command=browse)\
            .grid(row=3, column=1, padx=12, pady=6, sticky="e")

    def _change_theme(self, theme: str) -> None:
        ctk.set_appearance_mode(theme)
        self._set_cfg("theme", theme)

    def _set_cfg(self, key: str, value: str) -> None:
        self.config_data[key] = value
        save_config(self.config_data)
