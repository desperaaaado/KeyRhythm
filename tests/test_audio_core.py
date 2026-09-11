from __future__ import annotations

import unittest

from keyrhythm.audio.engine import slider_to_gain
from keyrhythm.audio.ring_buffer import SpscRingBuffer
from keyrhythm.audio.timeline import AudioTimeline


class AudioCoreTests(unittest.TestCase):
    def test_ring_buffer_capacity_and_fifo(self) -> None:
        ring: SpscRingBuffer[int] = SpscRingBuffer(2)
        self.assertTrue(ring.push(1))
        self.assertTrue(ring.push(2))
        self.assertFalse(ring.push(3))
        self.assertEqual(ring.overflows, 1)
        self.assertEqual(ring.pop(), 1)
        self.assertEqual(ring.pop(), 2)
        self.assertIsNone(ring.pop())

    def test_timeline_mapping_and_latency(self) -> None:
        timeline = AudioTimeline()
        timeline.begin(24_000, 1_000_000_000, 0.010)
        self.assertEqual(timeline.map_host_time(1_500_000_000), 48_000)
        self.assertEqual(timeline.presented_frame(1_500_000_000), 47_520)

    def test_volume_curve(self) -> None:
        self.assertEqual(slider_to_gain(0), 0)
        self.assertEqual(slider_to_gain(100), 1)
        self.assertAlmostEqual(slider_to_gain(50), 0.25)


if __name__ == "__main__":
    unittest.main()

