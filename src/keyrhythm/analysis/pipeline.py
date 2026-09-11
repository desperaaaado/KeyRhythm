from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from keyrhythm.config import CHART_SAMPLE_RATE
from keyrhythm.domain.chart import AnalysisManifest, Chart, ChartNote
from keyrhythm.domain.difficulty import generate_playable_charts, is_playable
from keyrhythm.resources import executable_path


class AnalysisUnavailableError(RuntimeError):
    pass


Progress = Callable[[str, float], None]


def _prepare_frozen_numba() -> None:
    if not getattr(sys, "frozen", False) or getattr(sys, "_keyrhythm_numba_ready", False):
        return
    import numba  # type: ignore
    if not getattr(numba, "_keyrhythm_no_cache", False):
        raise AnalysisUnavailableError("frozen Numba runtime hook was not loaded")
    sys._keyrhythm_numba_ready = True


def _emit(callback: Progress | None, stage: str, progress: float) -> None:
    if callback:
        callback(stage, progress)


def _parse_note_event(event: Any, index: int, time_offset: float = 0.0) -> ChartNote | None:
    try:
        if isinstance(event, dict):
            start = float(event.get("start_time", event.get("start", 0))) + time_offset
            end = float(event.get("end_time", event.get("end", start - time_offset))) + time_offset
            pitch = int(event.get("pitch_midi", event.get("pitch", 60)))
            confidence = float(event.get("amplitude", event.get("confidence", 0.5)))
        else:
            start, end, pitch, confidence = (
                float(event[0]) + time_offset, float(event[1]) + time_offset, int(event[2]), float(event[3])
            )
        duration = max(1, round((end - start) * CHART_SAMPLE_RATE))
        if duration < round(0.045 * CHART_SAMPLE_RATE):
            return None
        return ChartNote(
            id=f"n-{index:06d}",
            start_frame=max(0, round(start * CHART_SAMPLE_RATE)),
            duration_frames=duration,
            midi_pitch=max(0, min(127, pitch)),
            velocity=max(1, min(127, round(confidence * 127))),
            confidence=max(0.0, min(1.0, confidence)),
            source="basic_pitch",
        )
    except (KeyError, TypeError, ValueError, IndexError):
        return None


def select_melody(notes: list[ChartNote]) -> list[ChartNote]:
    accepted: list[ChartNote] = []
    for note in sorted(notes, key=lambda item: (item.start_frame, -item.confidence)):
        if note.confidence < 0.20:
            continue
        conflicts = [
            current
            for current in accepted[-8:]
            if min(current.end_frame, note.end_frame) - max(current.start_frame, note.start_frame) > CHART_SAMPLE_RATE // 20
        ]
        if conflicts:
            strongest = max(conflicts, key=lambda item: item.confidence)
            if strongest.confidence >= note.confidence:
                continue
            accepted.remove(strongest)
        accepted.append(note)
    accepted.sort(key=lambda item: (item.start_frame, item.midi_pitch))
    for index, note in enumerate(accepted, start=1):
        note.id = f"n-{index:06d}"
    return accepted


def _analyze_beats(audio_path: Path, librosa, soundfile_module) -> tuple[float, list[int]]:
    block_seconds = 60
    overlap_seconds = 2
    samplerate = soundfile_module.info(str(audio_path)).samplerate
    blocksize = block_seconds * samplerate
    overlap = overlap_seconds * samplerate
    step = blocksize - overlap
    tempos: list[float] = []
    beat_frames: list[int] = []
    for block_index, block in enumerate(soundfile_module.blocks(
        str(audio_path), blocksize=blocksize, overlap=overlap, dtype="float32", always_2d=True
    )):
        mono = block.mean(axis=1)
        tempo, beats = librosa.beat.beat_track(y=mono, sr=samplerate, units="time")
        value = float(tempo.item() if hasattr(tempo, "item") else tempo)
        if value > 0:
            tempos.append(value)
        offset_seconds = block_index * step / samplerate
        for beat in beats:
            frame = round((offset_seconds + float(beat)) * CHART_SAMPLE_RATE)
            if not beat_frames or frame - beat_frames[-1] > CHART_SAMPLE_RATE // 20:
                beat_frames.append(frame)
    bpm = sorted(tempos)[len(tempos) // 2] if tempos else 120.0
    return bpm, beat_frames


def _transcribe_windowed(audio_path: Path, duration_frames: int, predict, model_path) -> list[ChartNote]:
    duration_seconds = duration_frames / CHART_SAMPLE_RATE
    if duration_seconds <= 300:
        _model_output, _midi_data, events = predict(str(audio_path), model_path)
        return [note for index, event in enumerate(events, start=1) if (note := _parse_note_event(event, index))]
    ffmpeg = executable_path("ffmpeg.exe") or executable_path("ffmpeg")
    if not ffmpeg:
        raise AnalysisUnavailableError("ffmpeg is required for windowed transcription of long songs")
    window = 60.0
    overlap = 2.0
    step = window - overlap
    candidates: list[ChartNote] = []
    with tempfile.TemporaryDirectory(prefix="keyrhythm-analysis-") as directory:
        start = 0.0
        index = 1
        while start < duration_seconds:
            segment = Path(directory) / f"segment-{index:04d}.wav"
            result = subprocess.run(
                [
                    ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                    "-ss", f"{start:.6f}", "-t", str(window), "-i", str(audio_path),
                    "-ac", "1", "-ar", "22050", str(segment),
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "ffmpeg segment extraction failed")
            _model_output, _midi_data, events = predict(str(segment), model_path)
            last_window = start + window >= duration_seconds
            for event in events:
                local_start = float(event.get("start_time", event.get("start", 0))) if isinstance(event, dict) else float(event[0])
                local_end = float(event.get("end_time", event.get("end", local_start))) if isinstance(event, dict) else float(event[1])
                center = (local_start + local_end) / 2
                if start > 0 and center < overlap / 2:
                    continue
                if not last_window and center >= window - overlap / 2:
                    continue
                note = _parse_note_event(event, index, start)
                index += 1
                if note:
                    candidates.append(note)
            start += step
    return candidates


def analyze_audio(
    audio_path: Path,
    *,
    song_id: str,
    audio_sha256: str,
    duration_frames: int,
    progress: Progress | None = None,
) -> tuple[Chart, bool]:
    _prepare_frozen_numba()
    try:
        import librosa  # type: ignore
        import soundfile as sf  # type: ignore
        from basic_pitch import ICASSP_2022_MODEL_PATH  # type: ignore
        from basic_pitch.inference import predict  # type: ignore
    except ImportError as error:
        raise AnalysisUnavailableError(
            f"analysis dependency import failed: {error.name or error}; run tools/setup_environment.py"
        ) from error

    _emit(progress, "beat_detection", 0.0)
    bpm, beat_frames = _analyze_beats(audio_path, librosa, sf)
    _emit(progress, "beat_detection", 1.0)

    _emit(progress, "transcription", 0.0)
    candidates = _transcribe_windowed(audio_path, duration_frames, predict, ICASSP_2022_MODEL_PATH)
    _emit(progress, "transcription", 1.0)
    _emit(progress, "melody_selection", 0.0)
    notes = select_melody(candidates)
    notes = [note for note in notes if note.start_frame < duration_frames]
    for note in notes:
        note.duration_frames = min(note.duration_frames, duration_frames - note.start_frame)
    charts = generate_playable_charts(notes)
    _emit(progress, "melody_selection", 1.0)
    model_path = Path(ICASSP_2022_MODEL_PATH)
    model_hash = hashlib.sha256(model_path.read_bytes()).hexdigest() if model_path.is_file() else ""
    chart = Chart(
        song_id=song_id,
        audio_sha256=audio_sha256,
        duration_frames=duration_frames,
        notes=notes,
        charts=charts,
        estimated_bpm=bpm or 120.0,
        beat_frames=beat_frames,
        analysis_manifest=AnalysisManifest(
            transcriber="basic-pitch",
            model_version="0.4",
            model_hash=model_hash,
            parameters={"input_sample_rate": 22050, "melody_selection": "monophonic-v1", "window_seconds": 60},
        ),
    )
    chart.validate()
    return chart, is_playable(notes, charts)
