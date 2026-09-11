from __future__ import annotations

import hashlib
import math
import os
import struct
import wave
from pathlib import Path

from keyrhythm.config import AppPaths, CHART_SAMPLE_RATE
from keyrhythm.domain.chart import AnalysisManifest, Chart, ChartNote, save_chart_atomic
from keyrhythm.domain.difficulty import generate_playable_charts
from keyrhythm.domain.models import Song, SongStatus
from keyrhythm.library.importer import pcm_sha256
from keyrhythm.library.repository import SongRepository


PRESET_ID = "00000000-0000-4000-8000-000000000001"


def _generate_wav(path: Path, melody: list[tuple[int, int, int]]) -> None:
    duration_frames = melody[-1][1] + melody[-1][2] + CHART_SAMPLE_RATE
    temporary = path.with_suffix(".tmp.wav")
    with wave.open(str(temporary), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(CHART_SAMPLE_RATE)
        block = bytearray()
        for frame in range(duration_frames):
            value = 0.04 * math.sin(2 * math.pi * 130.8128 * frame / CHART_SAMPLE_RATE)
            for pitch, start, length in melody:
                if start <= frame < start + length:
                    local = frame - start
                    envelope = min(1.0, local / 480) * min(1.0, (length - local) / 2400)
                    frequency = 440 * 2 ** ((pitch - 69) / 12)
                    value += 0.18 * envelope * math.sin(2 * math.pi * frequency * local / CHART_SAMPLE_RATE)
            sample = max(-32767, min(32767, round(value * 32767)))
            block.extend(struct.pack("<hh", sample, sample))
            if len(block) >= 65_536:
                handle.writeframesraw(block)
                block.clear()
        if block:
            handle.writeframesraw(block)
    os.replace(temporary, path)


def ensure_builtin_song(paths: AppPaths, repository: SongRepository) -> Song:
    existing = repository.get(PRESET_ID)
    if existing and existing.normalized_path.is_file() and existing.chart_path and existing.chart_path.is_file():
        return existing
    directory = paths.library / PRESET_ID
    directory.mkdir(parents=True, exist_ok=True)
    normalized = directory / "normalized.wav"
    beat = CHART_SAMPLE_RATE // 2
    pitches = [60, 62, 64, 65, 67, 69, 71, 72, 72, 71, 69, 67, 65, 64, 62, 60]
    melody = [(pitch, CHART_SAMPLE_RATE + index * beat, round(beat * 0.8)) for index, pitch in enumerate(pitches)]
    if not normalized.exists():
        _generate_wav(normalized, melody)
    audio_hash, duration_frames = pcm_sha256(normalized)
    source = directory / "source.wav"
    if not source.exists():
        source.write_bytes(normalized.read_bytes())
    notes = [
        ChartNote(f"n-{index:06d}", start, length, pitch, velocity=92, confidence=1.0, source="preset")
        for index, (pitch, start, length) in enumerate(melody, start=1)
    ]
    chart = Chart(
        song_id=PRESET_ID,
        audio_sha256=audio_hash,
        duration_frames=duration_frames,
        notes=notes,
        charts=generate_playable_charts(notes),
        estimated_bpm=120,
        beat_frames=list(range(0, duration_frames, beat)),
        analysis_manifest=AnalysisManifest("manual", "builtin-1", "", {"license": "generated with application code"}),
    )
    chart_path = directory / "chart.json"
    save_chart_atomic(chart, chart_path, backup=False)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    song = Song(
        id=PRESET_ID,
        source_sha256=source_hash,
        audio_pcm_sha256=audio_hash,
        title="KeyRhythm 练习曲",
        artist="KeyRhythm",
        duration_frames=duration_frames,
        source_path=source,
        normalized_path=normalized,
        chart_path=chart_path,
        status=SongStatus.READY,
        analysis_version="builtin-1",
        tags=("预置", "练习"),
    )
    if existing:
        repository.delete(PRESET_ID)
    repository.add(song)
    return song

