from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from keyrhythm.domain.models import AnalysisJob, AnalysisStage, GameMode, Score, Song, SongStatus
from keyrhythm.library import Database, SongRepository
from keyrhythm.library.repository import DuplicateAudioError


class RepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp.name) / "test.db")
        self.database.migrate()
        self.repository = SongRepository(self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def song(identifier: str = "one", digest: str = "pcm-one") -> Song:
        return Song(
            id=identifier,
            source_sha256=f"source-{identifier}",
            audio_pcm_sha256=digest,
            title="夜曲",
            artist="测试艺术家",
            duration_frames=48_000,
            source_path=Path("source.wav"),
            normalized_path=Path("normalized.wav"),
            status=SongStatus.READY,
            tags=("钢琴", "安静"),
        )

    def test_crud_and_search(self) -> None:
        self.repository.add(self.song())
        self.assertEqual(self.repository.get("one").title, "夜曲")
        self.assertEqual(len(self.repository.search("测试艺术家")), 1)
        self.assertEqual(len(self.repository.search("钢琴")), 1)
        self.repository.delete("one")
        self.assertIsNone(self.repository.get("one"))

    def test_duplicate_pcm_is_rejected(self) -> None:
        self.repository.add(self.song())
        with self.assertRaises(DuplicateAudioError):
            self.repository.add(self.song("two", "pcm-one"))

    def test_score_and_analysis_job(self) -> None:
        self.repository.add(self.song())
        score_id = self.repository.save_score(Score(
            song_id="one", chart_revision=1, chart_hash="chart", mode=GameMode.PIANO,
            difficulty=None, total_score=1000, accuracy=1.0, max_combo=1,
            perfect_count=1, good_count=0, bad_count=0, wrong_count=0,
            miss_count=0, hold_break_count=0,
        ))
        self.assertGreater(score_id, 0)
        self.repository.upsert_analysis_job(AnalysisJob("job", "one", AnalysisStage.TRANSCRIPTION, 0.5))
        job = self.repository.get_analysis_job("job")
        self.assertEqual(job.stage, AnalysisStage.TRANSCRIPTION)
        self.assertEqual(job.progress, 0.5)


if __name__ == "__main__":
    unittest.main()
