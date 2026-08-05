"""Fenêtre de saisie de signature : tracé à la souris ou import d'une image."""

from tkinter import filedialog

import customtkinter as ctk

from core.pdf_editor import COLORS
from core.signature import render_signature

CANVAS_WIDTH = 520
CANVAS_HEIGHT = 200
INK_COLORS = ("Noir", "Bleu", "Rouge")


class SignatureDialog(ctk.CTkToplevel):
    """Boîte modale renvoyant le chemin d'un PNG de signature dans `result`.

    Usage :
        dlg = SignatureDialog(parent)
        parent.wait_window(dlg)
        if dlg.result: ...
    """

    def __init__(self, master) -> None:
        super().__init__(master)
        self.result: str | None = None
        self._strokes: list[list[tuple[float, float]]] = []
        self._current: list[tuple[float, float]] = []

        self.title("Signature")
        self.geometry(f"{CANVAS_WIDTH + 60}x{CANVAS_HEIGHT + 170}")
        self.resizable(False, False)
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        ctk.CTkLabel(self, text="Tracez votre signature avec la souris :",
                     anchor="w").pack(fill="x", padx=20, pady=(14, 6))

        self.canvas = ctk.CTkCanvas(self, width=CANVAS_WIDTH, height=CANVAS_HEIGHT,
                                    bg="#ffffff", highlightthickness=1,
                                    highlightbackground="#888888", cursor="pencil")
        self.canvas.pack(padx=20)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(opts, text="Encre :").pack(side="left")
        self.color_menu = ctk.CTkOptionMenu(opts, width=110, values=list(INK_COLORS))
        self.color_menu.set("Noir")
        self.color_menu.pack(side="left", padx=(6, 16))
        ctk.CTkLabel(opts, text="Épaisseur :").pack(side="left")
        self.width_menu = ctk.CTkOptionMenu(opts, width=70, values=["2", "3", "5", "8"])
        self.width_menu.set("3")
        self.width_menu.pack(side="left", padx=6)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(4, 14))
        ctk.CTkButton(actions, text="Effacer", width=90, fg_color="#555",
                      command=self._clear).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Importer une image...", width=170,
                      command=self._import_image).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Valider", width=90,
                      command=self._validate).pack(side="right", padx=4)
        ctk.CTkButton(actions, text="Annuler", width=90, fg_color="#8a3333",
                      command=self._cancel).pack(side="right", padx=4)

        self.error_label = ctk.CTkLabel(self, text="", text_color="#e05555", anchor="w")
        self.error_label.pack(fill="x", padx=20, pady=(0, 8))

    # ------------------------------------------------------------- dessin
    def _ink(self) -> str:
        """Couleur d'encre courante, au format hexadécimal pour le canvas Tk."""
        r, g, b = COLORS[self.color_menu.get()]
        return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"

    def _on_press(self, event) -> None:
        self._current = [(event.x, event.y)]

    def _on_drag(self, event) -> None:
        if not self._current:
            return
        x0, y0 = self._current[-1]
        self.canvas.create_line(x0, y0, event.x, event.y, fill=self._ink(),
                                width=int(self.width_menu.get()),
                                capstyle="round", smooth=True)
        self._current.append((event.x, event.y))

    def _on_release(self, event) -> None:
        if self._current:
            self._strokes.append(self._current)
            self._current = []

    def _clear(self) -> None:
        self._strokes.clear()
        self._current = []
        self.canvas.delete("all")
        self.error_label.configure(text="")

    # ------------------------------------------------------------ actions
    def _import_image(self) -> None:
        """Utilise une image existante (photo ou scan d'une signature)."""
        path = filedialog.askopenfilename(
            title="Choisir une image de signature",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp")],
        )
        if path:
            self.result = path
            self.destroy()

    def _validate(self) -> None:
        """Convertit le tracé en PNG transparent et ferme la fenêtre."""
        try:
            r, g, b = COLORS[self.color_menu.get()]
            self.result = render_signature(
                self._strokes, color=(r, g, b), width=int(self.width_menu.get())
            )
        except ValueError as e:
            self.error_label.configure(text=str(e))
            return
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
