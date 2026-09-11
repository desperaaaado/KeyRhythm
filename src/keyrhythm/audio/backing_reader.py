from __future__ import annotations

import threading
import time
import wave
from pathlib import Path

from keyrhythm.config import CHART_SAMPLE_RATE


class BackingReaderError(RuntimeError):
    pass


class _FloatFrameRing:
    def __init__(self, capacity_frames: int, numpy_module):
        self.np = numpy_module
        self.buffer = self.np.zeros((capacity_frames + 1, 2), dtype=self.np.float32)
        self.size = capacity_frames + 1
        self.head = 0
        self.tail = 0

    def available_read(self) -> int:
        return (self.head - self.tail) % self.size

    def available_write(self) -> int:
        return self.size - 1 - self.available_read()

    def write(self, frames) -> int:
        count = min(len(frames), self.available_write())
        if count <= 0:
            return 0
        first = min(count, self.size - self.head)
        self.buffer[self.head:self.head + first] = frames[:first]
        second = count - first
        if second:
            self.buffer[:second] = frames[first:first + second]
        self.head = (self.head + count) % self.size
        return count

    def read_into(self, output) -> int:
        count = min(len(output), self.available_read())
        if count <= 0:
            return 0
        first = min(count, self.size - self.tail)
        output[:first] = self.buffer[self.tail:self.tail + first]
        second = count - first
        if second:
            output[first:first + second] = self.buffer[:second]
        self.tail = (self.tail + count) % self.size
        return count


class WaveBackingReader:
    def __init__(self, path: Path, numpy_module, capacity_seconds: int = 2):
        self.path = path
        self.np = numpy_module
        with wave.open(str(path), "rb") as handle:
            if (
                handle.getframerate() != CHART_SAMPLE_RATE
                or handle.getnchannels() != 2
                or handle.getsampwidth() != 2
            ):
                raise BackingReaderError("expected 48 kHz stereo PCM16 WAV")
            self.duration_frames = handle.getnframes()
        self.ring = _FloatFrameRing(CHART_SAMPLE_RATE * capacity_seconds, numpy_module)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._start_frame = 0
        self.eof = False
        self.error: str | None = None

    def start(self, start_frame: int) -> None:
        self.stop()
        self.ring.head = self.ring.tail = 0
        self._start_frame = max(0, min(start_frame, self.duration_frames))
        self._stop.clear()
        self.eof = False
        self.error = None
        self._thread = threading.Thread(target=self._run, name="backing-reader", daemon=True)
        self._thread.start()

    def wait_until_primed(self, minimum_frames: int = 4096, timeout: float = 2.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.ring.available_read() >= minimum_frames or self.eof or self.error:
                return self.error is None
            time.sleep(0.005)
        return False

    def read_into(self, output) -> int:
        return self.ring.read_into(output)

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def _run(self) -> None:
        try:
            with wave.open(str(self.path), "rb") as handle:
                handle.setpos(self._start_frame)
                while not self._stop.is_set():
                    writable = self.ring.available_write()
                    if writable < 4096:
                        time.sleep(0.003)
                        continue
                    raw = handle.readframes(min(writable, 16_384))
                    if not raw:
                        self.eof = True
                        return
                    frames = self.np.frombuffer(raw, dtype="<i2").reshape(-1, 2).astype(self.np.float32)
                    frames *= 1.0 / 32768.0
                    offset = 0
                    while offset < len(frames) and not self._stop.is_set():
                        written = self.ring.write(frames[offset:])
                        offset += written
                        if written == 0:
                            time.sleep(0.002)
        except Exception as error:
            self.error = str(error)

