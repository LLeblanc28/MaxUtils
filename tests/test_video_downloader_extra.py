"""Couvre le hook de progression interne et les branches fmt/quality de
VideoDownloader.download() non exercées par usage_test.py."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.video_downloader import CancelledError, VideoDownloader


def _patch_ydl(captured_opts: dict):
    """Simule yt_dlp.YoutubeDL tout en capturant les options passées (dont
    le hook de progression), pour pouvoir l'invoquer manuellement ensuite."""

    def factory(opts):
        captured_opts.update(opts)
        ydl_instance = MagicMock()
        ydl_instance.extract_info.return_value = {"title": "video", "ext": "mp4"}
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
        self.assertTrue(out.endswith(".mp3"))
        self.assertEqual(captured["postprocessors"][0]["preferredquality"], "320")

    def test_download_mp4_with_explicit_quality(self):
        captured: dict = {}
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("core.video_downloader.yt_dlp.YoutubeDL", side_effect=_patch_ydl(captured)), \
                 patch("core.video_downloader.get_ffmpeg_path", return_value=None):
                VideoDownloader().download("https://example.com", tmp_dir, fmt="mp4", quality="720p")
        self.assertIn("height<=720", captured["format"])


if __name__ == "__main__":
    unittest.main()
