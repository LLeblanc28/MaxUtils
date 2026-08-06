"""Fenêtre principale : onglets Vidéo / Convertisseur / PDF + paramètres."""

import os
import threading
from tkinter import filedialog

import customtkinter as ctk

from core.updater import current_version, update_yt_dlp
from ui.dnd import enable_dnd
from ui.tab_converter import ConverterTab
from ui.tab_pdf import PdfTab
from ui.tab_pdf_editor import PdfEditorTab
from ui.tab_pdf_tools import PdfToolsTab
from ui.tab_video import VideoTab
from utils.config import (
    APP_NAME,
    APP_VERSION,
    MIN_WINDOW_SIZE,
    load_config,
    resource_path,
    save_config,
)
from utils.i18n import set_language, t

TAB_KEYS = ("📥 Vidéo", "🔄 Convertisseur", "📄 Fusion PDF",
            "✏️ Éditeur PDF", "🧰 Outils PDF")


class MultiToolApp(ctk.CTk):
    """Fenêtre principale de l'application."""

    def __init__(self) -> None:
        super().__init__()
        self.config_data = load_config()

        # Doit précéder toute création de widget : les libellés sont traduits
        # au moment où ils sont construits.
        set_language(self.config_data["language"])

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

        # Doit précéder la création des onglets : les cibles de dépôt ne
        # peuvent s'enregistrer qu'une fois tkdnd chargé sur la racine.
        self.dnd_enabled = enable_dnd(self)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Barre du haut : titre + bouton paramètres
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(header, text=t("🛠️ Multi-Outils"), font=ctk.CTkFont(size=18, weight="bold"))\
            .grid(row=0, column=0, sticky="w")
        ctk.CTkButton(header, text="⚙️", width=40, command=self._open_settings)\
            .grid(row=0, column=1, sticky="e")

        # Onglets
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        # Les onglets sont ajoutés puis retrouvés par leur libellé : il doit
        # donc être traduit une seule fois, et réutilisé tel quel des deux côtés.
        names = [t(key) for key in TAB_KEYS]
        for name in names:
            self.tabview.add(name)

        VideoTab(self.tabview.tab(names[0]), self).pack(fill="both", expand=True)
        ConverterTab(self.tabview.tab(names[1]), self).pack(fill="both", expand=True)
        PdfTab(self.tabview.tab(names[2]), self).pack(fill="both", expand=True)
        PdfEditorTab(self.tabview.tab(names[3]), self).pack(fill="both", expand=True)
        PdfToolsTab(self.tabview.tab(names[4]), self).pack(fill="both", expand=True)

    # -------------------------------------------------------------- settings
    def _open_settings(self) -> None:
        """Ouvre la fenêtre de paramètres (thème, dossier, langue)."""
        win = ctk.CTkToplevel(self)
        win.title(t("Paramètres"))
        win.geometry("520x420")
        win.grab_set()
        win.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(win, text=t("Thème :")).grid(row=0, column=0, padx=12, pady=12, sticky="w")
        theme_menu = ctk.CTkOptionMenu(win, values=["dark", "light"],
                                       command=self._change_theme)
        theme_menu.set(self.config_data["theme"])
        theme_menu.grid(row=0, column=1, padx=12, pady=12, sticky="ew")

        ctk.CTkLabel(win, text=t("Langue :")).grid(row=1, column=0, padx=12, pady=12, sticky="w")
        lang_menu = ctk.CTkOptionMenu(win, values=["fr", "en"],
                                      command=self._change_language)
        lang_menu.set(self.config_data["language"])
        lang_menu.grid(row=1, column=1, padx=12, pady=12, sticky="ew")

        # Les libellés sont traduits à la construction des widgets : rebâtir
        # toute l'interface à chaud ferait perdre le travail en cours (PDF
        # ouvert, listes de fichiers). Mieux vaut l'annoncer clairement.
        self.language_hint = ctk.CTkLabel(win, text="", anchor="w", text_color="#4d9bff")
        self.language_hint.grid(row=6, column=0, columnspan=2, padx=12, pady=(4, 8), sticky="w")

        ctk.CTkLabel(win, text=t("Dossier de sortie :")).grid(row=2, column=0, padx=12, pady=12, sticky="w")
        out_entry = ctk.CTkEntry(win)
        out_entry.insert(0, self.config_data["output_dir"])
        out_entry.grid(row=2, column=1, padx=12, pady=12, sticky="ew")

        def browse() -> None:
            folder = filedialog.askdirectory(initialdir=out_entry.get())
            if folder:
                out_entry.delete(0, "end")
                out_entry.insert(0, folder)
                self._set_cfg("output_dir", folder)

        ctk.CTkButton(win, text=t("Parcourir..."), command=browse)\
            .grid(row=3, column=1, padx=12, pady=6, sticky="e")

        # yt-dlp est le seul paquet qui se périme vite : les plateformes vidéo
        # changent leurs API souvent, et une version figée finit par ne plus
        # rien télécharger. Le mettre à jour ne doit pas exiger un terminal.
        ctk.CTkLabel(win, text=t("Téléchargeur vidéo :"))\
            .grid(row=4, column=0, padx=12, pady=(18, 6), sticky="w")
        self.update_label = ctk.CTkLabel(
            win, text=f"yt-dlp {current_version()}", anchor="w")
        self.update_label.grid(row=4, column=1, padx=12, pady=(18, 6), sticky="ew")
        self.update_btn = ctk.CTkButton(win, text=t("Mettre à jour yt-dlp"),
                                        command=self._update_yt_dlp)
        self.update_btn.grid(row=5, column=1, padx=12, pady=6, sticky="e")

    def _update_yt_dlp(self) -> None:
        """Lance la mise à jour en tâche de fond, sans figer la fenêtre."""
        self.update_btn.configure(state="disabled")
        self.update_label.configure(text=t("Mise à jour en cours..."))

        def worker() -> None:
            ok, message = update_yt_dlp()
            self.after(0, lambda: self._show_update_result(ok, message))

        threading.Thread(target=worker, daemon=True).start()

    def _show_update_result(self, ok: bool, message: str) -> None:
        """Affiche le résultat de la mise à jour dans la fenêtre de paramètres."""
        try:
            self.update_label.configure(
                text=message, text_color="#4caf50" if ok else "#e05555")
            self.update_btn.configure(state="normal")
        except Exception:
            pass  # fenêtre de paramètres refermée entre-temps : rien à afficher

    def _change_language(self, language: str) -> None:
        """Enregistre la langue et prévient qu'elle s'applique au redémarrage."""
        self._set_cfg("language", language)
        self.language_hint.configure(
            text=t("Le changement de langue s'applique au redémarrage."))

    def _change_theme(self, theme: str) -> None:
        ctk.set_appearance_mode(theme)
        self._set_cfg("theme", theme)

    def _set_cfg(self, key: str, value: str) -> None:
        self.config_data[key] = value
        save_config(self.config_data)
