"""Widgets partagés entre les onglets (zone de log colorée)."""

import tkinter as tk
from datetime import datetime

import customtkinter as ctk

from utils.i18n import t, untranslate


def bind_memory(app, menu, key: str) -> None:
    """Restaure le dernier choix fait dans un menu, et retient les suivants.

    La valeur est mémorisée sous son libellé français, jamais sous celui
    affiché : sans cela, un réglage enregistré en anglais ne serait plus
    reconnu après un passage en français.

    Le `command` déjà posé sur le menu est conservé et appelé ensuite : la
    mémorisation s'ajoute au comportement existant au lieu de le remplacer.
    """
    recall = getattr(app, "recall", None)
    remember = getattr(app, "remember", None)
    if recall is None or remember is None:
        return  # objet d'application sans mémoire (doublure de test)

    stored = recall(key, "")
    if stored:
        label = t(stored)
        if label in menu.cget("values"):
            menu.set(label)

    previous = menu.cget("command")

    def on_change(choice: str) -> None:
        remember(key, untranslate(choice))
        if previous:
            previous(choice)

    menu.configure(command=on_change)


class LogBox(ctk.CTkFrame):
    """Zone de log colorée : rouge = erreur, vert = succès, gris = info.

    Thread-safe : les écritures passent par `after()` du widget.
    """

    COLORS = {"error": "#e05555", "success": "#4caf50", "info": "#9e9e9e"}

    def __init__(self, master, height: int = 120, **kwargs) -> None:
        super().__init__(master, **kwargs)
        self.text = tk.Text(
            self, height=6, wrap="word", state="disabled",
            bg="#1a1a1a", fg="#d0d0d0", relief="flat",
            font=("Consolas", 10), insertbackground="#d0d0d0",
        )
        self.text.pack(fill="both", expand=True, padx=4, pady=4)
        for tag, color in self.COLORS.items():
            self.text.tag_configure(tag, foreground=color)

    def log(self, message: str, level: str = "info") -> None:
        """Ajoute une ligne de log (appelable depuis n'importe quel thread)."""
        self.after(0, self._append, message, level)

    def _append(self, message: str, level: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.text.configure(state="normal")
        self.text.insert("end", f"[{ts}] {message}\n", level)
        self.text.see("end")
        self.text.configure(state="disabled")
