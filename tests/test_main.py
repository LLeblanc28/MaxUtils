"""Couvre le point d'entrée main.py sans ouvrir de vraie fenêtre."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main


class TestMain(unittest.TestCase):
    def test_main_creates_app_and_runs_mainloop(self):
        with patch("main.MultiToolApp") as mock_app_cls:
            main.main()
        mock_app_cls.assert_called_once_with()
        mock_app_cls.return_value.mainloop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
