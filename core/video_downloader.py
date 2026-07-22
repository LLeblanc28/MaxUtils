"""Téléchargement et conversion de vidéos via yt-dlp (YouTube, Vimeo, TikTok...).

Le téléchargement tourne dans un thread appelant ; ce module expose une classe
annulable avec callbacks de progression.
"""

import threading
from pathlib import Path
from typing import Callable

import yt_dlp

from utils.config import get_ffmpeg_path
from utils.security import ensure_within_directory, validate_url


class CancelledError(Exception):
    """Levée quand l'utilisateur annule le téléchargement."""


class VideoDownloader:
    """Encapsule yt-dlp : récupération d'infos, téléchargement MP3/MP4, annulation."""

    def __init__(self) -> None:
        self._cancel_event = threading.Event()

    # ------------------------------------------------------------------ infos
    @staticmethod
    def fetch_info(url: str) -> dict:
        """Récupère titre, durée et miniature d'une URL sans télécharger.

        Raises:
            SecurityError: URL pointant vers un hôte local/interne ou un schéma non http(s).
            yt_dlp.utils.DownloadError: URL invalide, vidéo privée, réseau...
        """
        validate_url(url)
        opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return {
            "title": info.get("title", "Sans titre"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader", ""),
        }

    # ------------------------------------------------------------- download
    def cancel(self) -> None:
        """Demande l'annulation du téléchargement en cours."""
        self._cancel_event.set()

    def download(
        self,
        url: str,
        output_dir: str,
        fmt: str = "mp4",
        quality: str = "Meilleure",
        bitrate: str = "192",
        progress_callback: Callable[[dict], None] | None = None,
    ) -> str:
        """Télécharge une vidéo en MP4 ou l'extrait en MP3.

        Args:
            url: URL de la vidéo.
            output_dir: dossier de destination.
            fmt: "mp4" ou "mp3".
            quality: pour MP4 : "360p", "480p", "720p", "1080p", "Meilleure".
            bitrate: pour MP3 : "128", "192" ou "320" (kbps).
            progress_callback: reçoit un dict avec percent, speed, eta, total.

        Returns:
            Chemin du fichier téléchargé.

        Raises:
            SecurityError: URL pointant vers un hôte local/interne ou un schéma non http(s),
                ou chemin de sortie s'échappant du dossier de destination.
            CancelledError: si annulé par l'utilisateur.
            yt_dlp.utils.DownloadError: erreur réseau ou vidéo indisponible.
        """
        validate_url(url)
        output_dir_path = Path(output_dir).resolve()
        self._cancel_event.clear()
        result: dict = {}

        def hook(d: dict) -> None:
            if self._cancel_event.is_set():
                raise CancelledError("Téléchargement annulé.")
            if d["status"] == "downloading" and progress_callback:
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes", 0)
                progress_callback({
                    "percent": done / total if total else 0.0,
                    "speed": d.get("speed"),
                    "eta": d.get("eta"),
                    "total": total,
                })
            elif d["status"] == "finished":
                result["filepath"] = d.get("filename")

        opts: dict = {
            "outtmpl": "%(title)s.%(ext)s",
            "paths": {"home": str(output_dir_path)},
            # Empêche un titre de vidéo malveillant (ex: "../../Windows/System32/x")
            # d'écrire en dehors du dossier de destination (C-01, path traversal).
            "restrictfilenames": True,
            "windowsfilenames": True,
            "progress_hooks": [hook],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        ffmpeg = get_ffmpeg_path()
        if ffmpeg:
            opts["ffmpeg_location"] = str(Path(ffmpeg).parent)

        if fmt == "mp3":
            opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": bitrate,
                }],
            })
        else:  # mp4
            if quality == "Meilleure":
                fmt_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            else:
                h = quality.rstrip("p")
                fmt_str = (
                    f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]"
                    f"/best[height<={h}][ext=mp4]/best[height<={h}]/best"
                )
            opts.update({"format": fmt_str, "merge_output_format": "mp4"})

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = Path(ydl.prepare_filename(info)).name

        if fmt == "mp3":
            filename = str(Path(filename).with_suffix(".mp3"))

        final_path = result.get("filepath") or str(output_dir_path / filename)
        # Troisième couche de défense : même si restrictfilenames/paths étaient
        # contournés par une version future de yt-dlp, le chemin final est
        # revérifié avant d'être retourné à l'appelant.
        return str(ensure_within_directory(final_path, output_dir_path))
