from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from keyrhythm.config import AppPaths, _default_data_root


class AppPathsTests(unittest.TestCase):
    def test_source_default_is_project_data_directory(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            paths = AppPaths.discover()

        project_root = Path(__file__).resolve().parents[1]
        self.assertEqual(paths.root, project_root / "data")
        self.assertEqual(paths.library, project_root / "data" / "library")

    def test_environment_override_still_takes_priority(self) -> None:
        target = Path("D:/custom-keyrhythm-data").resolve()
        with patch.dict(os.environ, {"KEYRHYTHM_DATA_DIR": str(target)}, clear=True):
            paths = AppPaths.discover()

        self.assertEqual(paths.root, target)

    def test_frozen_app_inside_project_uses_project_data_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = Path(temporary_directory)
            (project_root / "pyproject.toml").touch()
            executable = project_root / "dist" / "KeyRhythm" / "KeyRhythm.exe"
            with (
                patch("keyrhythm.config.sys.frozen", True, create=True),
                patch("keyrhythm.config.sys.executable", str(executable)),
            ):
                self.assertEqual(_default_data_root(), project_root / "data")

    def test_installed_frozen_app_uses_local_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            local_app_data = Path(temporary_directory) / "LocalAppData"
            executable = local_app_data / "Programs" / "KeyRhythm" / "KeyRhythm.exe"
            with (
                patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}, clear=True),
                patch("keyrhythm.config.sys.frozen", True, create=True),
                patch("keyrhythm.config.sys.executable", str(executable)),
            ):
                self.assertEqual(_default_data_root(), local_app_data.resolve() / "KeyRhythm")


if __name__ == "__main__":
    unittest.main()
