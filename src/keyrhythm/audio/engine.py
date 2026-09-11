from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from keyrhythm.audio.backing_reader import WaveBackingReader
from keyrhythm.audio.devices import resolve_output_device
from keyrhythm.audio.ring_buffer import SpscRingBuffer
from keyrhythm.audio.synthesizer import FluidSynthSynthesizer, SineSynthesizer, Synthesizer
from keyrhythm.audio.timeline import AudioTimeline
from keyrhythm.config import CHART_SAMPLE_RATE
from keyrhythm.domain.models import (
    AudioBus,
    AudioDiagnostics,
    AudioTimelineSnapshot,
    InputAction,
    InputEvent,
    PlaybackState,
)
from keyrhythm.resources import resource_path

try:
    import numpy as np  # type: ignore
    import sounddevice as sd  # type: ignore
except ImportError:
    np = None
    sd = None


class AudioUnavailableError(RuntimeError):
    pass


InputMappedCallback = Callable[[InputEvent, int], None]


def slider_to_gain(value: int) -> float:
    normalized = max(0.0, min(1.0, value / 100.0))
    return normalized * normalized


class AudioEngine:
    MAX_CALLBACK_FRAMES = 8192

    def __init__(
        self,
        *,
        soundfont: Path | None = None,
        fluidsynth_library: Path | None = None,
        output_device: str | int | None = None,
        on_input_mapped: InputMappedCallback | None = None,
    ):
        if np is None or sd is None:
            raise AudioUnavailableError("install KeyRhythm with the 'app' extra to enable audio")
        self.timeline = AudioTimeline()
        self.state = PlaybackState.EMPTY
        self.events: SpscRingBuffer[InputEvent] = SpscRingBuffer(2048)
        self.reader: WaveBackingReader | None = None
        self.stream = None
        bundled_soundfont = resource_path("assets/soundfonts/default.sf2")
        bundled_fluidsynth = resource_path("bin/libfluidsynth-3.dll")
        self.soundfont = soundfont or (bundled_soundfont if bundled_soundfont.is_file() else None)
        self.fluidsynth_library = fluidsynth_library or (bundled_fluidsynth if bundled_fluidsynth.is_file() else None)
        self.output_device = output_device
        self._last_error: str | None = None
        self.synth: Synthesizer = self._create_synth()
        self.on_input_mapped = on_input_mapped
        self._synth_buffer = np.zeros((self.MAX_CALLBACK_FRAMES, 2), dtype=np.float32)
        self._gains = {
            AudioBus.BACKING: slider_to_gain(70),
            AudioBus.INSTRUMENT: slider_to_gain(90),
            AudioBus.MASTER: slider_to_gain(80),
        }
        self._current_gains = dict(self._gains)
        self._xruns = 0
        self._clipping = 0
        self._panic_requested = False
        self._last_overflow_count = 0
        self._block_size = 0

    @property
    def session_generation(self) -> int:
        return self.timeline.generation

    def _create_synth(self) -> Synthesizer:
        if self.soundfont:
            try:
                return FluidSynthSynthesizer(np, CHART_SAMPLE_RATE, self.soundfont, self.fluidsynth_library)
            except Exception as error:
                self._last_error = f"FluidSynth unavailable; using sine fallback: {error}"
        return SineSynthesizer(np, CHART_SAMPLE_RATE, self.MAX_CALLBACK_FRAMES)

    def load_song(self, audio_path: Path, start_frame: int = 0) -> None:
        self.stop()
        self.reader = WaveBackingReader(audio_path, np)
        self.timeline.seek(start_frame, time.monotonic_ns())
        self.state = PlaybackState.READY

    def play(self) -> None:
        if self.reader is None:
            raise RuntimeError("load_song must be called first")
        if self.state == PlaybackState.PLAYING:
            return
        start_frame = self.timeline.rendered_frame
        self.reader.start(start_frame)
        if not self.reader.wait_until_primed():
            raise AudioUnavailableError(self.reader.error or "backing reader did not prime")
        self.stream = sd.OutputStream(
            device=resolve_output_device(sd, self.output_device),
            samplerate=CHART_SAMPLE_RATE,
            channels=2,
            dtype="float32",
            latency="low",
            blocksize=0,
            callback=self._callback,
            finished_callback=self._finished,
        )
        latency = float(self.stream.latency)
        now = time.monotonic_ns()
        self.timeline.stream_origin_ns = now
        self.timeline.stream_origin_chart_frame = start_frame
        self.timeline.output_latency_frames = round(latency * CHART_SAMPLE_RATE)
        self.state = PlaybackState.PLAYING
        self.stream.start()

    def pause(self) -> None:
        if self.state != PlaybackState.PLAYING:
            return
        presented = self.timeline.presented_frame(time.monotonic_ns())
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if self.reader:
            self.reader.stop()
        self.synth.all_notes_off()
        self.events.clear()
        self.timeline.rendered_frame = presented
        self.timeline.stream_origin_chart_frame = presented
        self.timeline.stream_origin_ns = time.monotonic_ns()
        self.state = PlaybackState.PAUSED

    def resume(self) -> None:
        if self.state == PlaybackState.PAUSED:
            self.play()

    def seek(self, target_frame: int) -> None:
        was_playing = self.state == PlaybackState.PLAYING
        self.pause()
        self.timeline.seek(max(0, target_frame), time.monotonic_ns())
        self.events.clear()
        self.synth.all_notes_off()
        self.state = PlaybackState.READY
        if was_playing:
            self.play()

    def stop(self) -> None:
        if getattr(self, "stream", None):
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if getattr(self, "reader", None):
            self.reader.stop()
        if getattr(self, "synth", None):
            self.synth.all_notes_off()
        if getattr(self, "events", None):
            self.events.clear()
        if getattr(self, "state", PlaybackState.EMPTY) != PlaybackState.EMPTY:
            self.timeline.seek(0, time.monotonic_ns())
            self.state = PlaybackState.STOPPED

    def close(self) -> None:
        self.stop()
        self.synth.close()

    def submit_input(self, event: InputEvent) -> bool:
        if event.session_generation != self.timeline.generation:
            return False
        accepted = self.events.push(event)
        if not accepted:
            self._panic_requested = True
        return accepted

    def map_input_time(self, host_time_ns: int) -> int:
        return self.timeline.map_host_time(host_time_ns)

    def set_bus_volume(self, bus: AudioBus, value: int) -> None:
        self._gains[bus] = slider_to_gain(value)

    def get_timeline_snapshot(self) -> AudioTimelineSnapshot:
        now = time.monotonic_ns()
        presented = self.timeline.presented_frame(now) if self.state == PlaybackState.PLAYING else self.timeline.rendered_frame
        return AudioTimelineSnapshot(
            session_generation=self.timeline.generation,
            state=self.state,
            chart_frame=presented,
            rendered_frame=self.timeline.rendered_frame,
            presented_frame=presented,
            output_latency_frames=self.timeline.output_latency_frames,
        )

    def get_diagnostics(self) -> AudioDiagnostics:
        cpu_load = float(self.stream.cpu_load) if self.stream else 0.0
        latency = float(self.stream.latency) if self.stream else self.timeline.output_latency_frames / CHART_SAMPLE_RATE
        return AudioDiagnostics(
            sample_rate=CHART_SAMPLE_RATE,
            block_size=self._block_size,
            output_latency_seconds=latency,
            cpu_load=cpu_load,
            xruns=self._xruns,
            queue_overflows=self.events.overflows,
            clipping_events=self._clipping,
            last_error=self._last_error,
        )

    def _dispatch(self, event: InputEvent) -> None:
        pitch = event.midi_pitch
        if pitch is None:
            return
        if event.action == InputAction.PRESS:
            self.synth.note_on(pitch, 96)
        else:
            self.synth.note_off(pitch)

    def _callback(self, outdata, frames: int, time_info, status) -> None:
        self._block_size = frames
        if frames > self.MAX_CALLBACK_FRAMES:
            outdata.fill(0)
            self._last_error = f"callback block too large: {frames}"
            self.state = PlaybackState.FAILED
            return
        if status:
            self._xruns += 1
        if self.state != PlaybackState.PLAYING or self.reader is None:
            outdata.fill(0)
            return
        if self._panic_requested or self.events.overflows != self._last_overflow_count:
            self.synth.all_notes_off()
            self.events.clear()
            self._last_overflow_count = self.events.overflows
            self._panic_requested = False
            self._last_error = "input event queue overflow"
            self.state = PlaybackState.FAILED
            outdata.fill(0)
            return

        read = self.reader.read_into(outdata)
        if read < frames:
            outdata[read:].fill(0)
            if not self.reader.eof:
                self._xruns += 1
                self._last_error = self.reader.error or "backing buffer underflow"
                self.state = PlaybackState.FAILED
        self._synth_buffer[:frames].fill(0)
        block_start = self.timeline.rendered_frame
        rendered = 0
        while True:
            event = self.events.pop()
            if event is None:
                break
            mapped = self.timeline.map_host_time(event.host_time_ns)
            offset = max(rendered, min(frames, mapped - block_start))
            self.synth.render_into(self._synth_buffer, rendered, offset)
            self._dispatch(event)
            if self.on_input_mapped:
                self.on_input_mapped(event, mapped)
            rendered = offset
        self.synth.render_into(self._synth_buffer, rendered, frames)

        smoothing = min(1.0, frames / (0.020 * CHART_SAMPLE_RATE))
        for bus in self._current_gains:
            self._current_gains[bus] += (self._gains[bus] - self._current_gains[bus]) * smoothing
        outdata *= self._current_gains[AudioBus.BACKING]
        outdata += self._synth_buffer[:frames] * self._current_gains[AudioBus.INSTRUMENT]
        outdata *= self._current_gains[AudioBus.MASTER]
        if np.any(np.abs(outdata) > 1.0):
            self._clipping += 1
        np.clip(outdata, -1.0, 1.0, out=outdata)
        self.timeline.advance_rendered(frames)

    def _finished(self) -> None:
        if self.state == PlaybackState.PLAYING:
            self.state = PlaybackState.STOPPED
