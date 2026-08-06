"""Onglet Éditeur PDF : texte, signature, formes, flèches et filigrane.

L'aperçu affiche la page rendue par PyMuPDF, sur laquelle les annotations sont
redessinées en surimpression. L'aperçu et le rendu final partagent le même
repère (origine en haut à gauche, Y vers le bas) : la seule conversion est le
facteur de zoom, ce qui garantit que ce qui est vu est ce qui est écrit.
"""

import io
import threading
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from core.pdf_editor import COLORS, FONT_FAMILIES, Annotation, PdfEditor, Style, Watermark
from ui.dnd import register_drop_target
from ui.signature_dialog import SignatureDialog
from ui.widgets import LogBox
from utils.i18n import t, tl, untranslate
from utils.security import SecurityError

TOOL_LABELS = (
    ("text", "🅰  Texte"),
    ("signature", "✍  Signature"),
    ("line", "╱  Ligne"),
    ("arrow", "➜  Flèche"),
    ("rect", "▭  Rectangle"),
    ("ellipse", "◯  Ellipse"),
    ("highlight", "▬  Surlignage"),
)

FONT_SIZES = ["8", "10", "12", "14", "18", "24", "32", "48", "64"]
LINE_WIDTHS = ["1", "2", "3", "5", "8"]
OPACITIES = ["25 %", "50 %", "75 %", "100 %"]
ZOOM_LEVELS = ["50 %", "75 %", "100 %", "125 %", "150 %"]
NO_FILL = "Aucun"


class PdfEditorTab(ctk.CTkFrame):
    """UI d'édition : palette d'outils, propriétés, aperçu cliquable, filigrane."""

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.editor: PdfEditor | None = None
        self.annotations: list[Annotation] = []
        self.page_index = 0
        self.zoom = 1.0
        self._photo = None            # référence forte : sinon Tk libère l'image
        self._preview_images: list = []  # idem pour les aperçus de signature
        self._drag_start: tuple[float, float] | None = None
        self._rubber_band: int | None = None
        self._pending_signature: str | None = None
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 5))
        ctk.CTkButton(top, text=t("📂 Ouvrir un PDF"), command=self._open_pdf).pack(side="left", padx=5)
        self.file_label = ctk.CTkLabel(top, text=t("Aucun fichier chargé."), anchor="w")
        self.file_label.pack(side="left", padx=10)

        self._build_sidebar()
        self._build_canvas()
        self._build_bottom()

        self.logbox = LogBox(self)
        self.logbox.grid(row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=(5, 10))

    def _build_sidebar(self) -> None:
        side = ctk.CTkScrollableFrame(self, label_text=t("Outils & propriétés"), width=250)
        side.grid(row=1, column=0, sticky="ns", padx=(10, 5), pady=5)

        self.tool_var = ctk.StringVar(value="text")
        for value, label in TOOL_LABELS:
            ctk.CTkRadioButton(side, text=t(label), variable=self.tool_var, value=value,
                               command=self._on_tool_change).pack(anchor="w", pady=3, padx=6)

        ctk.CTkLabel(side, text=t("── Texte ──"), anchor="w").pack(fill="x", pady=(12, 2), padx=6)
        self.family_menu = self._labeled_menu(side, "Police", list(FONT_FAMILIES), "Helvetica")
        self.size_menu = self._labeled_menu(side, "Taille", FONT_SIZES, "14")

        styles = ctk.CTkFrame(side, fg_color="transparent")
        styles.pack(fill="x", padx=6, pady=4)
        self.bold_var = ctk.BooleanVar(value=False)
        self.italic_var = ctk.BooleanVar(value=False)
        self.underline_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(styles, text=t("Gras"), width=70, checkbox_width=18, checkbox_height=18,
                        variable=self.bold_var,
                        font=ctk.CTkFont(weight="bold")).pack(side="left", padx=(0, 6))
        ctk.CTkCheckBox(styles, text=t("Ital."), width=70, checkbox_width=18, checkbox_height=18,
                        variable=self.italic_var,
                        font=ctk.CTkFont(slant="italic")).pack(side="left", padx=6)
        ctk.CTkCheckBox(styles, text=t("Soul."), width=70, checkbox_width=18, checkbox_height=18,
                        variable=self.underline_var,
                        font=ctk.CTkFont(underline=True)).pack(side="left", padx=6)

        ctk.CTkLabel(side, text=t("── Tracé ──"), anchor="w").pack(fill="x", pady=(12, 2), padx=6)
        self.color_menu = self._labeled_menu(side, "Couleur", tl(COLORS), t("Noir"))
        self.fill_menu = self._labeled_menu(side, "Remplissage",
                                            tl([NO_FILL] + list(COLORS)), t(NO_FILL))
        self.width_menu = self._labeled_menu(side, "Épaisseur", LINE_WIDTHS, "2")
        self.opacity_menu = self._labeled_menu(side, "Opacité", OPACITIES, "100 %")

        ctk.CTkLabel(side, text=t("── Filigrane ──"), anchor="w").pack(fill="x", pady=(12, 2), padx=6)
        self.watermark_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(side, text=t("Filigrane sur toutes les pages"),
                        variable=self.watermark_var,
                        command=self._render).pack(anchor="w", padx=6, pady=4)
        self.watermark_entry = ctk.CTkEntry(side, placeholder_text="CONFIDENTIEL")
        self.watermark_entry.insert(0, "CONFIDENTIEL")
        self.watermark_entry.pack(fill="x", padx=6, pady=4)
        # L'aperçu suit la saisie : le filigrane se met à jour à chaque frappe.
        self.watermark_entry.bind("<KeyRelease>", lambda _e: self._render())
        self.wm_color_menu = self._labeled_menu(side, "Couleur", tl(COLORS), t("Rouge"),
                                                command=lambda _v: self._render())
        self.wm_size_menu = self._labeled_menu(side, "Taille", ["40", "60", "80", "100"], "60",
                                               command=lambda _v: self._render())
        self.wm_opacity_menu = self._labeled_menu(side, "Intensité",
                                                  ["25 %", "45 %", "65 %", "85 %"], "45 %",
                                                  command=lambda _v: self._render())

    def _labeled_menu(self, parent, label: str, values: list[str], default: str, command=None):
        """Ajoute une ligne « libellé + menu déroulant » et retourne le menu."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=6, pady=3)
        ctk.CTkLabel(row, text=t(label), width=95, anchor="w").pack(side="left")
        menu = ctk.CTkOptionMenu(row, values=values, width=120, command=command)
        menu.set(default)
        menu.pack(side="right")
        return menu

    def _build_canvas(self) -> None:
        holder = ctk.CTkFrame(self)
        holder.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=5)
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        self.canvas = ctk.CTkCanvas(holder, bg="#3a3a3a", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar = ctk.CTkScrollbar(holder, orientation="vertical", command=self.canvas.yview)
        vbar.grid(row=0, column=1, sticky="ns")
        hbar = ctk.CTkScrollbar(holder, orientation="horizontal", command=self.canvas.xview)
        hbar.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(yscrollcommand=vbar.set, xscrollcommand=hbar.set)

        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        register_drop_target(self.canvas, self._on_drop)

    def _build_bottom(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=5)

        ctk.CTkButton(bar, text="◀", width=40, command=lambda: self._change_page(-1)).pack(side="left", padx=2)
        self.page_label = ctk.CTkLabel(bar, text="— / —", width=90)
        self.page_label.pack(side="left", padx=2)
        ctk.CTkButton(bar, text="▶", width=40, command=lambda: self._change_page(1)).pack(side="left", padx=2)

        self.zoom_menu = ctk.CTkOptionMenu(bar, values=ZOOM_LEVELS, width=100,
                                           command=self._on_zoom_change)
        self.zoom_menu.set("100 %")
        self.zoom_menu.pack(side="left", padx=(16, 2))

        ctk.CTkButton(bar, text=t("💾 Enregistrer sous..."), command=self._save).pack(side="right", padx=4)
        ctk.CTkButton(bar, text=t("🗑 Tout effacer"), fg_color="#8a3333",
                      command=self._clear_all).pack(side="right", padx=4)
        ctk.CTkButton(bar, text=t("↶ Annuler"), fg_color="#555",
                      command=self._undo).pack(side="right", padx=4)

    # -------------------------------------------------------- lecture UI
    @staticmethod
    def _percent(value: str) -> float:
        """Convertit « 75 % » en 0.75."""
        return float(value.replace("%", "").strip()) / 100.0

    def _current_style(self) -> Style:
        """Construit un Style à partir de l'état courant du panneau latéral.

        Les menus affichent des libellés traduits : chaque valeur lue est
        ramenée à sa clé française avant d'interroger COLORS ou FONT_FAMILIES.
        """
        fill_name = untranslate(self.fill_menu.get())
        return Style(
            family=FONT_FAMILIES[self.family_menu.get()],
            size=float(self.size_menu.get()),
            bold=self.bold_var.get(),
            italic=self.italic_var.get(),
            underline=self.underline_var.get(),
            color=COLORS[untranslate(self.color_menu.get())],
            fill=None if fill_name == NO_FILL else COLORS[fill_name],
            line_width=float(self.width_menu.get()),
            opacity=self._percent(self.opacity_menu.get()),
        )

    def _current_watermark(self) -> Watermark:
        """Construit le filigrane à partir de l'état courant du panneau."""
        return Watermark(
            enabled=self.watermark_var.get(),
            text=self.watermark_entry.get().strip() or "CONFIDENTIEL",
            size=float(self.wm_size_menu.get()),
            color=COLORS[untranslate(self.wm_color_menu.get())],
            opacity=self._percent(self.wm_opacity_menu.get()),
        )

    # ------------------------------------------------------------ fichier
    def _on_drop(self, paths) -> None:
        """Ouvre le premier PDF déposé : l'éditeur ne traite qu'un document."""
        if not paths:
            return
        if len(paths) > 1:
            self.logbox.log(t("Un seul PDF à la fois : le premier a été ouvert."))
        self._load_pdf(paths[0])

    def _open_pdf(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("PDF", "*.pdf")])
        if not path:
            return
        self._load_pdf(path)

    def _load_pdf(self, path: str) -> None:
        """Charge un PDF dans l'éditeur, en remplaçant celui déjà ouvert."""
        try:
            editor = PdfEditor(path)
        except SecurityError as e:
            self.logbox.log(t("⛔ {name} refusé (sécurité) : {error}").format(
                name=Path(path).name, error=e), "error")
            return
        except Exception as e:
            self.logbox.log(t("PDF illisible {name} : {error}").format(
                name=Path(path).name, error=e), "error")
            return

        if self.editor:
            self.editor.close()
        self.editor = editor
        self.annotations.clear()
        self.page_index = 0
        self.file_label.configure(text=f"{Path(path).name} — {editor.page_count} page(s)")
        self.logbox.log(t("Chargé : {name}").format(name=Path(path).name), "success")
        self._render()

    def _change_page(self, delta: int) -> None:
        if not self.editor:
            return
        new_index = self.page_index + delta
        if 0 <= new_index < self.editor.page_count:
            self.page_index = new_index
            self._render()

    def _on_zoom_change(self, value: str) -> None:
        self.zoom = self._percent(value)
        self._render()

    def _on_tool_change(self) -> None:
        self.logbox.log(t("Outil : {tool}").format(
            tool=t(dict(TOOL_LABELS)[self.tool_var.get()]).strip()))

    # ------------------------------------------------------------- rendu
    def _render(self) -> None:
        """Affiche la page courante et redessine les annotations par-dessus."""
        if not self.editor:
            return
        from PIL import Image, ImageTk

        # Le filigrane est rendu par le moteur, pas simulé sur le canvas :
        # l'aperçu est donc exactement l'image du PDF qui sera écrit.
        png = self.editor.render_page(self.page_index, self.zoom, self._current_watermark())
        image = Image.open(io.BytesIO(png))
        self._photo = ImageTk.PhotoImage(image)

        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._photo, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, image.width, image.height))
        self.page_label.configure(text=f"{self.page_index + 1} / {self.editor.page_count}")
        self._draw_overlay()

    def _draw_overlay(self) -> None:
        """Dessine sur le canvas les annotations de la page affichée."""
        self._preview_images = []
        z = self.zoom
        for ann in self.annotations:
            if ann.page != self.page_index:
                continue
            st = ann.style
            outline = self._hex(st.color)
            x0, y0, x1, y1 = (v * z for v in ann.rect)

            if ann.kind == "text":
                self.canvas.create_text(
                    ann.x0 * z, ann.y0 * z, text=ann.text, fill=outline, anchor="sw",
                    font=self._tk_font(st),
                )
            elif ann.kind == "signature":
                self._draw_signature_preview(ann, x0, y0, x1, y1)
            elif ann.kind in ("line", "arrow"):
                self.canvas.create_line(
                    ann.x0 * z, ann.y0 * z, ann.x1 * z, ann.y1 * z,
                    fill=outline, width=max(1, st.line_width * z),
                    arrow="last" if ann.kind == "arrow" else None,
                )
            elif ann.kind == "rect":
                self.canvas.create_rectangle(
                    x0, y0, x1, y1, outline=outline,
                    width=max(1, st.line_width * z),
                    fill=self._hex(st.fill) if st.fill else "",
                )
            elif ann.kind == "ellipse":
                self.canvas.create_oval(
                    x0, y0, x1, y1, outline=outline,
                    width=max(1, st.line_width * z),
                    fill=self._hex(st.fill) if st.fill else "",
                )
            else:  # highlight
                self.canvas.create_rectangle(
                    x0, y0, x1, y1, outline="",
                    fill=self._hex(st.fill or st.color), stipple="gray50",
                )

    def _draw_signature_preview(self, ann: Annotation, x0, y0, x1, y1) -> None:
        """Affiche la signature à l'échelle ; un cadre si l'image est illisible."""
        from PIL import Image, ImageTk

        width, height = max(1, int(x1 - x0)), max(1, int(y1 - y0))
        try:
            img = Image.open(ann.image_path).convert("RGBA")
            img.thumbnail((width, height))
            photo = ImageTk.PhotoImage(img)
            self._preview_images.append(photo)
            self.canvas.create_image(x0, y0, image=photo, anchor="nw")
        except Exception:
            self.canvas.create_rectangle(x0, y0, x1, y1, outline="#888888", dash=(4, 2))

    @staticmethod
    def _hex(rgb: tuple[float, float, float]) -> str:
        """Convertit une couleur RGB 0-1 en notation hexadécimale Tk."""
        r, g, b = rgb
        return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"

    def _tk_font(self, st: Style) -> tuple:
        """Police Tk approchant le rendu PDF, pour l'aperçu à l'écran."""
        family = {"helv": "Helvetica", "tiro": "Times", "cour": "Courier"}[st.family]
        modifiers = []
        if st.bold:
            modifiers.append("bold")
        if st.italic:
            modifiers.append("italic")
        if st.underline:
            modifiers.append("underline")
        return (family, max(1, int(st.size * self.zoom)), " ".join(modifiers) or "normal")

    # ------------------------------------------------------- interactions
    def _canvas_point(self, event) -> tuple[float, float]:
        """Position du curseur en points PDF (tient compte du défilement et du zoom)."""
        return (self.canvas.canvasx(event.x) / self.zoom,
                self.canvas.canvasy(event.y) / self.zoom)

    def _on_press(self, event) -> None:
        if not self.editor:
            self.logbox.log(t("Ouvrez d'abord un PDF."), "error")
            return
        x, y = self._canvas_point(event)
        if self.tool_var.get() == "text":
            self._add_text(x, y)
            return
        self._drag_start = (x, y)

    def _on_drag(self, event) -> None:
        """Trace un rectangle élastique pour matérialiser la zone en cours."""
        if not self._drag_start:
            return
        x, y = self._canvas_point(event)
        if self._rubber_band is not None:
            self.canvas.delete(self._rubber_band)
        z = self.zoom
        self._rubber_band = self.canvas.create_rectangle(
            self._drag_start[0] * z, self._drag_start[1] * z, x * z, y * z,
            outline="#4d9bff", dash=(4, 2),
        )

    def _on_release(self, event) -> None:
        if not self._drag_start:
            return
        x0, y0 = self._drag_start
        x1, y1 = self._canvas_point(event)
        self._drag_start = None
        if self._rubber_band is not None:
            self.canvas.delete(self._rubber_band)
            self._rubber_band = None

        # Un simple clic (sans glisser) ne définit aucune zone exploitable.
        if abs(x1 - x0) < 3 and abs(y1 - y0) < 3:
            self.logbox.log(t("Glissez la souris pour définir la zone."), "error")
            return

        kind = self.tool_var.get()
        if kind == "signature":
            self._add_signature(x0, y0, x1, y1)
            return
        self.annotations.append(
            Annotation(kind, self.page_index, x0, y0, x1, y1, style=self._current_style())
        )
        self.logbox.log(t("{tool} ajouté(e).").format(
            tool=t(dict(TOOL_LABELS)[kind]).strip()), "success")
        self._render()

    def _add_text(self, x: float, y: float) -> None:
        """Demande le contenu puis pose le texte au point cliqué."""
        dialog = ctk.CTkInputDialog(text=t("Texte à insérer :"), title=t("Ajouter du texte"))
        content = dialog.get_input()
        if not content:
            return
        self.annotations.append(
            Annotation("text", self.page_index, x, y, text=content, style=self._current_style())
        )
        self.logbox.log(t("Texte ajouté."), "success")
        self._render()

    def _add_signature(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """Ouvre la fenêtre de signature puis place l'image dans la zone tracée."""
        dialog = SignatureDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self.annotations.append(
            Annotation("signature", self.page_index, x0, y0, x1, y1,
                       image_path=dialog.result, style=self._current_style())
        )
        self.logbox.log(t("Signature ajoutée."), "success")
        self._render()

    # ------------------------------------------------------------ actions
    def _undo(self) -> None:
        if not self.annotations:
            self.logbox.log(t("Rien à annuler."), "error")
            return
        self.annotations.pop()
        self.logbox.log(t("Dernière annotation retirée."))
        self._render()

    def _clear_all(self) -> None:
        if not self.annotations:
            self.logbox.log(t("Aucune annotation à effacer."), "error")
            return
        self.annotations.clear()
        self.logbox.log(t("Toutes les annotations ont été retirées."))
        self._render()

    def _save(self) -> None:
        if not self.editor:
            self.logbox.log(t("Ouvrez d'abord un PDF."), "error")
            return
        watermark = self._current_watermark()
        if not self.annotations and not watermark.enabled:
            self.logbox.log(
                t("Rien à enregistrer : ajoutez une annotation ou un filigrane."), "error")
            return
        output = filedialog.asksaveasfilename(defaultextension=".pdf",
                                              filetypes=[("PDF", "*.pdf")])
        if not output:
            return

        annotations = list(self.annotations)

        def worker() -> None:
            try:
                path = self.editor.save(output, annotations, watermark)
                self.logbox.log(t("PDF enregistré : {path}").format(path=path), "success")
            except SecurityError as e:
                self.logbox.log(t("⛔ Sécurité : {error}").format(error=e), "error")
            except Exception as e:
                self.logbox.log(t("Erreur d'enregistrement : {error}").format(error=e), "error")

        threading.Thread(target=worker, daemon=True).start()
