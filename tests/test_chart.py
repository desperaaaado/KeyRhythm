from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from keyrhythm.config import CHART_SAMPLE_RATE
from keyrhythm.domain.chart import Chart, ChartNote, load_chart, save_chart_atomic
from keyrhythm.domain.difficulty import generate_playable_charts


def sample_chart() -> Chart:
    notes = [
        ChartNote("n-000001", 48_000, 12_000, 60, confidence=0.9),
        ChartNote("n-000002", 72_000, 12_000, 64, confidence=0.8),
        ChartNote("n-000003", 96_000, 12_000, 67, confidence=0.7),
    ]
    return Chart("song", "abc", 192_000, notes, generate_playable_charts(notes), beat_frames=[0, 24_000, 48_000])


class ChartTests(unittest.TestCase):
    def test_round_trip_and_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chart.json"
            chart = sample_chart()
            save_chart_atomic(chart, path)
            chart.chart_revision = 2
            save_chart_atomic(chart, path)
            loaded = load_chart(path)
            self.assertEqual(loaded.chart_revision, 2)
            self.assertTrue((path.parent / "chart.backup.json").is_file())

    def test_v1_migration(self) -> None:
        raw = {
            "schema_version": 1,
            "song_id": "song",
            "audio_sha256": "abc",
            "duration_ms": 2000,
            "audio_offset_ms": 10,
            "tempo": {"estimated_bpm": 120, "beats_ms": [0, 500]},
            "notes": [{
                "id": "n-000001", "start_ms": 1000, "duration_ms": 250,
                "midi_pitch": 60, "velocity": 90, "confidence": 0.9,
                "source": "test", "manually_edited": False,
            }],
            "charts": {"piano": {"note_ids": ["n-000001"]}, "lane_4_easy": {"events": [{"note_id": "n-000001", "lane": 2}]}},
        }
        chart = Chart.from_dict(raw)
        self.assertEqual(chart.schema_version, 3)
        self.assertEqual(chart.chart_revision, 2)
        self.assertEqual(chart.notes[0].start_frame, CHART_SAMPLE_RATE)
        self.assertEqual(chart.audio_offset_frames, 480)

    def test_load_v2_creates_backup_and_persists_v3(self) -> None:
        chart = sample_chart()
        raw = chart.to_dict()
        raw["schema_version"] = 2
        raw["chart_revision"] = 4
        raw["charts"] = {
            "piano": {"id": "piano", "mode": "piano", "difficulty": None, "lane_count": None, "note_ids": [note.id for note in chart.notes]},
            "lane_4_easy": {"id": "lane_4_easy", "mode": "lane", "difficulty": "easy", "lane_count": 4, "events": []},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chart.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            loaded = load_chart(path)
            self.assertEqual(loaded.schema_version, 3)
            self.assertEqual(loaded.chart_revision, 5)
            self.assertTrue((path.parent / "chart.backup-v2.json").is_file())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema_version"], 3)

    def test_invalid_reference_is_rejected(self) -> None:
        chart = sample_chart()
        chart.charts["lane_4_easy"].events[0].note_id = "missing"
        with self.assertRaises(ValueError):
            chart.validate()


if __name__ == "__main__":
    unittest.main()
