from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog

from keyrhythm.ui.main_window import MainWindow


class BlockingImporter:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def import_file(self, _path: Path, *, progress):
        progress("validate", 0.25)
        self.started.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("test importer was not released")
        return SimpleNamespace(title="Imported song")


class ImportUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(
            os.environ, {"KEYRHYTHM_DATA_DIR": self.directory.name}
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.directory.cleanup()

    def _wait_until(self, predicate, timeout: float = 5.0) -> None:
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                self.fail("timed out waiting for Qt event")
            self.app.processEvents()
            time.sleep(0.01)

    def test_import_worker_is_retained_until_background_task_finishes(self) -> None:
        window = MainWindow()
        importer = BlockingImporter()
        window.importer = importer
        source = Path(self.directory.name) / "song.mp3"

        try:
            with patch.object(QFileDialog, "getOpenFileName", return_value=(str(source), "")):
                window.import_song()

            self._wait_until(importer.started.is_set)
            self.assertIsNotNone(window.import_worker)
            self.assertIsNotNone(window.import_thread)
            self.assertTrue(window.import_thread.isRunning())
            self._wait_until(lambda: window.import_progress.value() == 250)

            importer.release.set()
            self._wait_until(lambda: window.import_thread is None)
            self.assertIsNone(window.import_worker)
            self.assertTrue(window.import_card.isHidden())
        finally:
            importer.release.set()
            if window.import_thread is not None:
                window.import_thread.quit()
                window.import_thread.wait(5000)
            window.close()


if __name__ == "__main__":
    unittest.main()
