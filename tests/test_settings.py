from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from keyrhythm.settings import Settings


class SettingsTests(unittest.TestCase):
    def test_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            Settings(master_volume=42, judgement_offset_frames=-96).save(path)
            loaded = Settings.load(path)
            self.assertEqual(loaded.master_volume, 42)
            self.assertEqual(loaded.judgement_offset_frames, -96)


if __name__ == "__main__":
    unittest.main()

