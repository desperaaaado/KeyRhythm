from __future__ import annotations

import unittest

from keyrhythm.config import CHART_SAMPLE_RATE
from keyrhythm.domain.chart import ChartNote, KeyEvent, PlayableChart
from keyrhythm.domain.models import Difficulty, GameMode, Judgement
from keyrhythm.gameplay.judgement import JudgementEngine


class JudgementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.note = ChartNote("n-1", CHART_SAMPLE_RATE, CHART_SAMPLE_RATE, 64)
        self.lane = PlayableChart(
            "lane_4_easy", GameMode.LANE, Difficulty.EASY, 4,
            [KeyEvent("n-1", 2)], [60, 62, 64, 65],
        )

    def test_boundaries(self) -> None:
        for delta_ms, expected in ((45, Judgement.PERFECT), (90, Judgement.GOOD), (150, Judgement.BAD)):
            with self.subTest(delta_ms=delta_ms):
                engine = JudgementEngine([self.note], self.lane)
                result = engine.press(CHART_SAMPLE_RATE + round(delta_ms * 48), key_index=2)
                self.assertEqual(result.judgement, expected)

    def test_wrong_lane_is_consumed_and_sounds_offset(self) -> None:
        engine = JudgementEngine([self.note], self.lane)
        result = engine.press(CHART_SAMPLE_RATE, key_index=0)
        self.assertEqual(result.judgement, Judgement.WRONG)
        self.assertEqual(result.sounding_pitch, 60)
        self.assertEqual(engine.press(CHART_SAMPLE_RATE, key_index=2).judgement, Judgement.GHOST)

    def test_ghost_does_not_consume_future_note(self) -> None:
        engine = JudgementEngine([self.note], self.lane)
        self.assertEqual(engine.press(0, key_index=2).judgement, Judgement.GHOST)
        self.assertEqual(engine.press(CHART_SAMPLE_RATE, key_index=2).judgement, Judgement.PERFECT)

    def test_early_release_breaks_hold(self) -> None:
        engine = JudgementEngine([self.note], self.lane)
        engine.press(CHART_SAMPLE_RATE, key_index=2)
        result = engine.release(CHART_SAMPLE_RATE + CHART_SAMPLE_RATE // 4, key_index=2)
        self.assertIsNotNone(result)
        self.assertEqual(result.judgement, Judgement.HOLD_BREAK)

    def test_collect_miss(self) -> None:
        engine = JudgementEngine([self.note], self.lane)
        misses = engine.collect_misses(CHART_SAMPLE_RATE + round(0.151 * CHART_SAMPLE_RATE))
        self.assertEqual(misses[0].judgement, Judgement.MISS)


if __name__ == "__main__":
    unittest.main()
