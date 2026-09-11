from __future__ import annotations

import ctypes
import ctypes.util
import math
import os
from pathlib import Path
from typing import Protocol


class Synthesizer(Protocol):
    def note_on(self, pitch: int, velocity: int) -> None: ...
    def note_off(self, pitch: int) -> None: ...
    def all_notes_off(self) -> None: ...
    def render_into(self, output, start: int, end: int) -> None: ...
    def close(self) -> None: ...


class SineSynthesizer:
    """Small dependency-free instrument fallback used until a SoundFont is configured."""

    def __init__(self, numpy_module, sample_rate: int, max_frames: int = 8192, voices: int = 32):
        self.np = numpy_module
        self.sample_rate = sample_rate
        self.active = [False] * voices
        self.pitches = [0] * voices
        self.phases = [0.0] * voices
        self.gains = [0.0] * voices
        self.index = self.np.arange(max_frames, dtype=self.np.float32)
        self.scratch = self.np.zeros(max_frames, dtype=self.np.float32)

    def note_on(self, pitch: int, velocity: int) -> None:
        slot = next((index for index, active in enumerate(self.active) if not active), 0)
        self.active[slot] = True
        self.pitches[slot] = pitch
        self.phases[slot] = 0.0
        self.gains[slot] = max(0.02, min(0.18, velocity / 1270.0))

    def note_off(self, pitch: int) -> None:
        for index, active in enumerate(self.active):
            if active and self.pitches[index] == pitch:
                self.active[index] = False

    def all_notes_off(self) -> None:
        for index in range(len(self.active)):
            self.active[index] = False

    def render_into(self, output, start: int, end: int) -> None:
        count = end - start
        if count <= 0:
            return
        output[start:end].fill(0)
        for voice, active in enumerate(self.active):
            if not active:
                continue
            frequency = 440.0 * (2.0 ** ((self.pitches[voice] - 69) / 12.0))
            omega = 2.0 * math.pi * frequency / self.sample_rate
            self.np.multiply(self.index[:count], omega, out=self.scratch[:count])
            self.scratch[:count] += self.phases[voice]
            self.np.sin(self.scratch[:count], out=self.scratch[:count])
            self.scratch[:count] *= self.gains[voice]
            output[start:end, 0] += self.scratch[:count]
            output[start:end, 1] += self.scratch[:count]
            self.phases[voice] = float((self.phases[voice] + omega * count) % (2.0 * math.pi))

    def close(self) -> None:
        self.all_notes_off()


class FluidSynthSynthesizer:
    def __init__(self, numpy_module, sample_rate: int, soundfont: Path, library_path: Path | None = None):
        self.np = numpy_module
        self._dll_directory = None
        if os.name == "nt" and library_path and hasattr(os, "add_dll_directory"):
            # Python 3.8+ uses the secure Windows DLL search path.  Keep this
            # handle alive so libfluidsynth can resolve bundled sndfile.dll.
            self._dll_directory = os.add_dll_directory(str(library_path.parent.resolve()))
        library = str(library_path) if library_path else ctypes.util.find_library("fluidsynth")
        if not library:
            raise RuntimeError("FluidSynth library was not found")
        self.settings = None
        self.synth = None
        try:
            self.lib = ctypes.CDLL(library)
            self._configure_api()
            self.settings = self.lib.new_fluid_settings()
            if not self.settings:
                raise RuntimeError("could not create FluidSynth settings")
            self.lib.fluid_settings_setnum(self.settings, b"synth.sample-rate", ctypes.c_double(sample_rate))
            self.synth = self.lib.new_fluid_synth(self.settings)
            if not self.synth:
                raise RuntimeError("could not create FluidSynth instance")
            if self.lib.fluid_synth_sfload(self.synth, str(soundfont).encode("utf-8"), 1) < 0:
                raise RuntimeError(f"could not load SoundFont: {soundfont}")
        except Exception:
            self.close()
            raise

    def _configure_api(self) -> None:
        self.lib.new_fluid_settings.restype = ctypes.c_void_p
        self.lib.delete_fluid_settings.argtypes = [ctypes.c_void_p]
        self.lib.new_fluid_synth.argtypes = [ctypes.c_void_p]
        self.lib.new_fluid_synth.restype = ctypes.c_void_p
        self.lib.delete_fluid_synth.argtypes = [ctypes.c_void_p]
        self.lib.fluid_settings_setnum.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_double]
        self.lib.fluid_synth_sfload.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        self.lib.fluid_synth_noteon.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.lib.fluid_synth_noteoff.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        self.lib.fluid_synth_cc.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.lib.fluid_synth_write_float.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
        ]

    def note_on(self, pitch: int, velocity: int) -> None:
        self.lib.fluid_synth_noteon(self.synth, 0, pitch, velocity)

    def note_off(self, pitch: int) -> None:
        self.lib.fluid_synth_noteoff(self.synth, 0, pitch)

    def all_notes_off(self) -> None:
        self.lib.fluid_synth_cc(self.synth, 0, 123, 0)

    def render_into(self, output, start: int, end: int) -> None:
        count = end - start
        if count <= 0:
            return
        base = output.ctypes.data + start * 2 * output.itemsize
        self.lib.fluid_synth_write_float(
            self.synth, count, ctypes.c_void_p(base), 0, 2,
            ctypes.c_void_p(base), 1, 2,
        )

    def close(self) -> None:
        if getattr(self, "synth", None):
            self.all_notes_off()
            self.lib.delete_fluid_synth(self.synth)
            self.synth = None
        if getattr(self, "settings", None):
            self.lib.delete_fluid_settings(self.settings)
            self.settings = None
        if getattr(self, "_dll_directory", None):
            self._dll_directory.close()
            self._dll_directory = None
