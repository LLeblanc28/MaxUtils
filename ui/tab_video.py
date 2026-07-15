"""Onglet Vidéo : téléchargement URL → MP3/MP4 avec yt-dlp."""

import threading
from tkinter import filedialog

import customtkinter as ctk

from core.video_downloader import CancelledError, VideoDownloader
from ui.widgets import LogBox
from utils.config import MP3_BITRATES, MP4_QUALITIES
from utils.helpers import format_duration, human_size


class VideoTab(ctk.CTkFrame):
    """UI de téléchargement vidéo : URL, format, qualité, progression, annulation."""

    def __init__(self, master, app) -> None:
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.downloader = VideoDownloader()
        self._build()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        # URL + détection
        url_frame = ctk.CTkFrame(self)
        url_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        url_frame.grid_columnconfigure(0, weight=1)
        self.url_entry = ctk.CTkEntry(url_frame, placeholder_text="Collez une URL (YouTube, TikTok, Vimeo...)")
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(url_frame, text="Détecter", width=100, command=self._fetch_info)\
            .grid(row=0, column=1, padx=8, pady=8)

        self.info_label = ctk.CTkLabel(self, text="", anchor="w")
        self.info_label.grid(row=1, column=0, sticky="ew", padx=18)

        # Options format
        opts = ctk.CTkFrame(self)
        opts.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        self.format_var = ctk.StringVar(value="mp4")
        ctk.CTkRadioButton(opts, text="MP4 (vidéo)", variable=self.format_var,
                           value="mp4", command=self._on_format_change).grid(row=0, column=0, padx=10, pady=8)
        ctk.CTkRadioButton(opts, text="MP3 (audio)", variable=self.format_var,
                           value="mp3", command=self._on_format_change).grid(row=0, column=1, padx=10, pady=8)
        self.quality_menu = ctk.CTkOptionMenu(opts, values=MP4_QUALITIES)
        self.quality_menu.set("720p")
        self.quality_menu.grid(row=0, column=2, padx=10, pady=8)
        self.bitrate_menu = ctk.CTkOptionMenu(opts, values=[b + " kbps" for b in MP3_BITRATES])
        self.bitrate_menu.set("192 kbps")

        # Dossier destination
        dest = ctk.CTkFrame(self)
        dest.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        dest.grid_columnconfigure(0, weight=1)
        self.dest_entry = ctk.CTkEntry(dest)
        self.dest_entry.insert(0, self.app.config_data["output_dir"])
        self.dest_entry.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        ctk.CTkButton(dest, text="Parcourir...", width=100, command=self._browse)\
            .grid(row=0, column=1, padx=8, pady=8)

        # Actions + progression
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=4, column=0, sticky="ew", padx=10, pady=5)
        self.dl_btn = ctk.CTkButton(actions, text="Télécharger", command=self._start_download)
        self.dl_btn.pack(side="left", padx=5)
        self.cancel_btn = ctk.CTkButton(actions, text="Annuler", state="disabled",
                                        fg_color="#8a3333", command=self.downloader.cancel)
        self.cancel_btn.pack(side="left", padx=5)

        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.grid(row=5, column=0, sticky="ew", padx=10, pady=5)

        self.grid_rowconfigure(6, weight=1)
        self.logbox = LogBox(self)
        self.logbox.grid(row=6, column=0, sticky="nsew", padx=10, pady=(5, 10))

    # ------------------------------------------------------------- handlers
    def _on_format_change(self) -> None:
        if self.format_var.get() == "mp4":
            self.bitrate_menu.grid_forget()
            self.quality_menu.grid(row=0, column=2, padx=10, pady=8)
        else:
            self.quality_menu.grid_forget()
            self.bitrate_menu.grid(row=0, column=2, padx=10, pady=8)

    def _browse(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.dest_entry.get())
        if folder:
            self.dest_entry.delete(0, "end")
            self.dest_entry.insert(0, folder)

    def _fetch_info(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            self.logbox.log("Veuillez saisir une URL.", "error")
            return
        self.logbox.log("Récupération des informations...")

        def worker() -> None:
            try:
                info = VideoDownloader.fetch_info(url)
                text = f"🎬 {info['title']}  —  {format_duration(info['duration'])}"
                self.after(0, lambda: self.info_label.configure(text=text))
                self.logbox.log("Informations récupérées.", "success")
            except Exception as e:
                self.logbox.log(f"Erreur : {e}", "error")

        threading.Thread(target=worker, daemon=True).start()

    def _start_download(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            self.logbox.log("Veuillez saisir une URL.", "error")
            return
        fmt = self.format_var.get()
        quality = self.quality_menu.get()
        bitrate = self.bitrate_menu.get().split()[0]
        dest = self.dest_entry.get().strip()

        self.dl_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.set(0)
        self.logbox.log(f"Téléchargement en {fmt.upper()}...")

        def on_progress(d: dict) -> None:
            self.after(0, lambda: self.progress.set(d["percent"]))
            speed = human_size(d["speed"]) + "/s" if d.get("speed") else "?"
            eta = f"{d['eta']}s" if d.get("eta") else "?"
            if int(d["percent"] * 100) % 10 == 0:
                self.logbox.log(f"{d['percent']*100:.0f}% — {speed} — ETA {eta}")

        def worker() -> None:
            try:
                path = self.downloader.download(url, dest, fmt, quality, bitrate, on_progress)
                self.after(0, lambda: self.progress.set(1.0))
                self.logbox.log(f"Terminé : {path}", "success")
            except CancelledError:
                self.logbox.log("Téléchargement annulé.", "error")
            except Exception as e:
                self.logbox.log(f"Erreur : {e}", "error")
            finally:
                self.after(0, self._reset_buttons)

        threading.Thread(target=worker, daemon=True).start()

    def _reset_buttons(self) -> None:
        self.dl_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
