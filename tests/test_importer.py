from __future__ import annotations

import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from keyrhythm.config import CHART_SAMPLE_RATE
from keyrhythm.library.importer import pcm_sha256


class ImporterTests(unittest.TestCase):
    def test_pcm_hash_ignores_wave_container_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "a.wav"
            second = Path(directory) / "b.wav"
            frames = [round(math.sin(index / 20) * 1000) for index in range(1000)]
            for path in (first, second):
                with wave.open(str(path), "wb") as handle:
                    handle.setnchannels(2)
                    handle.setsampwidth(2)
                    handle.setframerate(CHART_SAMPLE_RATE)
                    handle.writeframes(b"".join(struct.pack("<hh", value, value) for value in frames))
            first_hash, count = pcm_sha256(first)
            second_hash, _ = pcm_sha256(second)
            self.assertEqual(first_hash, second_hash)
            self.assertEqual(count, len(frames))


if __name__ == "__main__":
    unittest.main()

