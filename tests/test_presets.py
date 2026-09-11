from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from keyrhythm.config import AppPaths
from keyrhythm.domain.chart import load_chart
from keyrhythm.library import Database, SongRepository
from keyrhythm.library.presets import ensure_builtin_song


class PresetTests(unittest.TestCase):
    def test_generated_preset_is_idempotent_and_playable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = AppPaths(root, root / "db.sqlite", root / "settings.json", root / "library", root / "staging", root / "logs", root / "models")
            paths.ensure()
            database = Database(paths.database)
            database.migrate()
            repository = SongRepository(database)
            first = ensure_builtin_song(paths, repository)
            second = ensure_builtin_song(paths, repository)
            self.assertEqual(first.id, second.id)
            chart = load_chart(first.chart_path)
            self.assertEqual(len(chart.notes), 16)
            self.assertEqual(set(chart.charts), {"piano", "lane_4_easy", "lane_6_normal", "lane_8_hard"})


if __name__ == "__main__":
    unittest.main()

