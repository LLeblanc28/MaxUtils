"""Téléchargement et conversion de vidéos via yt-dlp (YouTube, Vimeo, TikTok...).

Le téléchargement tourne dans un thread appelant ; ce module expose une classe
annulable avec callbacks de progression.
"""

import threading
from pathlib import Path
from typing import Callable

import yt_dlp

from utils.config import get_ffmpeg_path
from utils.helpers import parse_timecode
from utils.security import ensure_within_directory, validate_url

# Langues de sous-titres proposées. "" = ne rien télécharger.
SUBTITLE_LANGUAGES = {
    "Aucun": "",
    "Français": "fr",
    "Anglais": "en",
    "Espagnol": "es",
    "Allemand": "de",
    "Italien": "it",
}


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
        playlist: bool = False,
        subtitles: str = "",
        start: str = "",
        end: str = "",
    ) -> list[str]:
        """Télécharge une vidéo (ou une playlist) en MP4, ou l'extrait en MP3.

        Args:
            url: URL de la vidéo ou de la playlist.
            output_dir: dossier de destination.
            fmt: "mp4" ou "mp3".
            quality: pour MP4 : "360p", "480p", "720p", "1080p", "Meilleure".
            bitrate: pour MP3 : "128", "192" ou "320" (kbps).
            progress_callback: reçoit un dict avec percent, speed, eta, total.
            playlist: télécharge toute la playlist au lieu de la seule vidéo.
            subtitles: code de langue des sous-titres (ex. "fr"), vide = aucun.
            start, end: bornes de l'extrait à conserver ("1:20", "01:02:03").
                Vides = vidéo entière.

        Returns:
            Les chemins des fichiers téléchargés (un seul élément hors playlist).

        Raises:
            SecurityError: URL pointant vers un hôte local/interne ou un schéma non http(s),
                ou chemin de sortie s'échappant du dossier de destination.
            ValueError: horodatage invalide, ou fin antérieure au début.
            CancelledError: si annulé par l'utilisateur.
            yt_dlp.utils.DownloadError: erreur réseau ou vidéo indisponible.
        """
        validate_url(url)
        start_sec, end_sec = parse_timecode(start), parse_timecode(end)
        if start_sec is not None and end_sec is not None and end_sec <= start_sec:
            raise ValueError("La fin de l'extrait doit être postérieure au début.")

        output_dir_path = Path(output_dir).resolve()
        self._cancel_event.clear()
        result: dict = {"files": []}

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
                filename = d.get("filename")
                if filename:
                    result["files"].append(filename)

        # En playlist, le numéro d'ordre préfixe le nom : les vidéos restent
        # dans l'ordre de la liste, et deux titres identiques ne s'écrasent pas.
        template = "%(playlist_index)03d - %(title)s.%(ext)s" if playlist else "%(title)s.%(ext)s"
        opts: dict = {
            "outtmpl": template,
            "paths": {"home": str(output_dir_path)},
            # Empêche un titre de vidéo malveillant (ex: "../../Windows/System32/x")
            # d'écrire en dehors du dossier de destination (C-01, path traversal).
            "restrictfilenames": True,
            "windowsfilenames": True,
            "progress_hooks": [hook],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": not playlist,
        }

        if subtitles:
            opts.update({
                "writesubtitles": True,
                # Beaucoup de vidéos n'ont que des sous-titres générés
                # automatiquement : sans ceci, la case resterait sans effet.
                "writeautomaticsub": True,
                "subtitleslangs": [subtitles],
            })

        if start_sec is not None or end_sec is not None:
            from yt_dlp.utils import download_range_func

            opts["download_ranges"] = download_range_func(None, [(start_sec or 0, end_sec)])
            # Sans découpe sur image-clé, l'extrait démarre à la clé précédente
            # et déborde de plusieurs secondes sur ce qui a été demandé.
            opts["force_keyframes_at_cuts"] = True

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
            fallback = Path(ydl.prepare_filename(info)).name

        # Le hook enregistre chaque fichier terminé : c'est la seule source
        # fiable en playlist. Hors playlist il peut rester vide (média déjà
        # présent en cache), d'où le repli sur le nom calculé par yt-dlp.
        paths = result["files"] or [str(output_dir_path / fallback)]
        if fmt == "mp3":
            # Le hook rapporte le fichier d'origine (.webm, .m4a...) : c'est le
            # post-traitement qui produit le .mp3, après le dernier appel.
            paths = [str(Path(p).with_suffix(".mp3")) for p in paths]

        # Troisième couche de défense : le chemin réellement écrit est vérifié,
        # et non pas seulement son nom de fichier — n'en garder que le nom
        # masquerait une écriture hors du dossier au lieu de la signaler.
        return [str(ensure_within_directory(p, output_dir_path)) for p in paths]
