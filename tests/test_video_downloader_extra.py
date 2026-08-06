"""Couvre le hook de progression interne et les branches fmt/quality de
VideoDownloader.download() non exercées par usage_test.py."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.video_downloader import CancelledError, VideoDownloader


def _patch_ydl(captured_opts: dict, finished_files: list[str] | None = None):
    """Simule yt_dlp.YoutubeDL tout en capturant les options passées (dont
    le hook de progression), pour pouvoir l'invoquer manuellement ensuite.

    `finished_files` reproduit ce que fait yt-dlp pendant un vrai
    téléchargement : appeler les hooks avec le statut « finished » pour chaque
    fichier écrit — le seul mécanisme fiable pour connaître les fichiers d'une
    playlist.
    """

    def factory(opts):
        captured_opts.update(opts)
        ydl_instance = MagicMock()

        def extract_info(url, download=False):
            if download:
                for name in finished_files or []:
                    for hook in opts.get("progress_hooks", []):
                        hook({"status": "finished", "filename": name})
            return {"title": "video", "ext": "mp4"}

        ydl_instance.extract_info.side_effect = extract_info
        ydl_instance.prepare_filename.return_value = "video.mp4"
        ctx = MagicMock(__enter__=MagicMock(return_value=ydl_instance), __exit__=MagicMock(return_value=None))
        return ctx

    return factory


class TestProgressHook(unittest.TestCase):
    def test_hook_reports_downloading_percent(self):
        captured: dict = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("core.video_downloader.yt_dlp.YoutubeDL", side_effect=_patch_ydl(captured)), \
                 patch("core.video_downloader.get_ffmpeg_path", return_value=None):
                events = []
                VideoDownloader().download(
                    "https://example.com", tmp_dir, fmt="mp4",
                    progress_callback=lambda d: events.append(d),
                )
        hook = captured["progress_hooks"][0]
        hook({"status": "downloading", "total_bytes": 100, "downloaded_bytes": 25, "speed": 10, "eta": 5})
        self.assertEqual(events[-1]["percent"], 0.25)

    def test_hook_downloading_without_total_reports_zero_percent(self):
        captured: dict = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("core.video_downloader.yt_dlp.YoutubeDL", side_effect=_patch_ydl(captured)), \
                 patch("core.video_downloader.get_ffmpeg_path", return_value=None):
                events = []
                VideoDownloader().download(
                    "https://example.com", tmp_dir, fmt="mp4",
                    progress_callback=lambda d: events.append(d),
                )
        hook = captured["progress_hooks"][0]
        hook({"status": "downloading"})
        self.assertEqual(events[-1]["percent"], 0.0)

    def test_hook_finished_records_filepath(self):
        captured: dict = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("core.video_downloader.yt_dlp.YoutubeDL", side_effect=_patch_ydl(captured)), \
                 patch("core.video_downloader.get_ffmpeg_path", return_value=None):
                VideoDownloader().download("https://example.com", tmp_dir, fmt="mp4")
        hook = captured["progress_hooks"][0]
        hook({"status": "finished", "filename": str(Path(tmp_dir) / "video.mp4")})  # ne doit pas lever

    def test_hook_raises_cancelled_error_when_cancel_requested(self):
        captured: dict = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("core.video_downloader.yt_dlp.YoutubeDL", side_effect=_patch_ydl(captured)), \
                 patch("core.video_downloader.get_ffmpeg_path", return_value=None):
                downloader = VideoDownloader()
                downloader.download("https://example.com", tmp_dir, fmt="mp4")
        downloader.cancel()
        hook = captured["progress_hooks"][0]
        with self.assertRaises(CancelledError):
            hook({"status": "downloading", "total_bytes": 10, "downloaded_bytes": 1})


class TestFormatAndQualityBranches(unittest.TestCase):
    def test_download_mp3_uses_extract_audio_postprocessor(self):
        captured: dict = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("core.video_downloader.yt_dlp.YoutubeDL", side_effect=_patch_ydl(captured)), \
                 patch("core.video_downloader.get_ffmpeg_path", return_value=None):
                out = VideoDownloader().download("https://example.com", tmp_dir, fmt="mp3", bitrate="320")
        self.assertTrue(out[0].endswith(".mp3"))
        self.assertEqual(captured["postprocessors"][0]["preferredquality"], "320")

    def test_download_mp4_with_explicit_quality(self):
        captured: dict = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("core.video_downloader.yt_dlp.YoutubeDL", side_effect=_patch_ydl(captured)), \
                 patch("core.video_downloader.get_ffmpeg_path", return_value=None):
                VideoDownloader().download("https://example.com", tmp_dir, fmt="mp4", quality="720p")
        self.assertIn("height<=720", captured["format"])


class TestPlaylistSubtitlesAndTrimming(unittest.TestCase):
    def _download(self, captured, **kwargs):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("core.video_downloader.yt_dlp.YoutubeDL", side_effect=_patch_ydl(captured)), \
                 patch("core.video_downloader.get_ffmpeg_path", return_value=None):
                return VideoDownloader().download("https://example.com", tmp_dir, **kwargs)

    def test_playlist_disabled_by_default(self):
        captured: dict = {}
        self._download(captured)
        self.assertTrue(captured["noplaylist"])
        self.assertNotIn("playlist_index", captured["outtmpl"])

    def test_playlist_enabled_numbers_the_files(self):
        captured: dict = {}
        self._download(captured, playlist=True)
        self.assertFalse(captured["noplaylist"])
        # Le numéro d'ordre évite que deux titres identiques s'écrasent.
        self.assertIn("playlist_index", captured["outtmpl"])

    def test_subtitles_requested_include_automatic_ones(self):
        captured: dict = {}
        self._download(captured, subtitles="fr")
        self.assertTrue(captured["writesubtitles"])
        self.assertTrue(captured["writeautomaticsub"])
        self.assertEqual(captured["subtitleslangs"], ["fr"])

    def test_no_subtitle_options_when_none_requested(self):
        captured: dict = {}
        self._download(captured)
        self.assertNotIn("writesubtitles", captured)

    def test_trimming_sets_a_download_range_on_keyframes(self):
        captured: dict = {}
        self._download(captured, start="1:20", end="3:45")
        self.assertIn("download_ranges", captured)
        self.assertTrue(captured["force_keyframes_at_cuts"])

    def test_trimming_with_only_a_start(self):
        captured: dict = {}
        self._download(captured, start="0:30")
        self.assertIn("download_ranges", captured)

    def test_trimming_with_only_an_end(self):
        captured: dict = {}
        self._download(captured, end="2:00")
        self.assertIn("download_ranges", captured)

    def test_no_range_when_no_timecode_given(self):
        captured: dict = {}
        self._download(captured)
        self.assertNotIn("download_ranges", captured)

    def test_end_before_start_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            self._download({}, start="3:00", end="1:00")
        self.assertIn("postérieure", str(ctx.exception))

    def test_invalid_timecode_is_refused(self):
        with self.assertRaises(ValueError):
            self._download({}, start="hier soir")

    def test_every_playlist_item_is_returned(self):
        captured: dict = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            files = [str(Path(tmp_dir) / f"{i:03d} - titre.mp4") for i in (1, 2, 3)]
            with patch("core.video_downloader.yt_dlp.YoutubeDL",
                       side_effect=_patch_ydl(captured, finished_files=files)), \
                 patch("core.video_downloader.get_ffmpeg_path", return_value=None):
                paths = VideoDownloader().download("https://example.com", tmp_dir, playlist=True)

        self.assertEqual(len(paths), 3)
        self.assertTrue(all(p.endswith(".mp4") for p in paths))
        self.assertIn("001 - titre.mp4", paths[0])

    def test_playlist_in_mp3_reports_the_converted_extension(self):
        # Le hook rapporte le fichier source (.webm) ; c'est le post-traitement
        # qui produit le .mp3, après le dernier appel du hook.
        captured: dict = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            files = [str(Path(tmp_dir) / "001 - titre.webm"),
                     str(Path(tmp_dir) / "002 - titre.webm")]
            with patch("core.video_downloader.yt_dlp.YoutubeDL",
                       side_effect=_patch_ydl(captured, finished_files=files)), \
                 patch("core.video_downloader.get_ffmpeg_path", return_value=None):
                paths = VideoDownloader().download("https://example.com", tmp_dir,
                                                   fmt="mp3", playlist=True)

        self.assertEqual(len(paths), 2)
        self.assertTrue(all(p.endswith(".mp3") for p in paths))

    def test_file_written_outside_the_destination_is_refused(self):
        # Dernier rempart contre le path traversal : même si yt-dlp écrivait
        # ailleurs, le chemin retourné est revalidé.
        from utils.security import SecurityError

        captured: dict = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("core.video_downloader.yt_dlp.YoutubeDL",
                       side_effect=_patch_ydl(captured, finished_files=["../evade.mp4"])), \
                 patch("core.video_downloader.get_ffmpeg_path", return_value=None):
                with self.assertRaises(SecurityError):
                    VideoDownloader().download("https://example.com", tmp_dir)


if __name__ == "__main__":
    unittest.main()
