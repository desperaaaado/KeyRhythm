from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class SongStatus(StrEnum):
    IMPORTING = "importing"
    READY = "ready"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


class GameMode(StrEnum):
    PIANO = "piano"
    LANE = "lane"


class Difficulty(StrEnum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


class InputAction(StrEnum):
    PRESS = "press"
    RELEASE = "release"


class Judgement(StrEnum):
    PERFECT = "perfect"
    GOOD = "good"
    BAD = "bad"
    WRONG = "wrong"
    MISS = "miss"
    GHOST = "ghost"
    HOLD_BREAK = "hold_break"


class AudioBus(StrEnum):
    BACKING = "backing"
    INSTRUMENT = "instrument"
    MASTER = "master"


class PlaybackState(StrEnum):
    EMPTY = "empty"
    READY = "ready"
    PLAYING = "playing"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


class AnalysisStage(StrEnum):
    VALIDATE = "validate"
    NORMALIZE = "normalize"
    BEAT_DETECTION = "beat_detection"
    TRANSCRIPTION = "transcription"
    MELODY_SELECTION = "melody_selection"
    DIFFICULTY_GENERATION = "difficulty_generation"
    VALIDATION = "validation"
    COMMIT = "commit"


@dataclass(slots=True)
class Song:
    id: str
    source_sha256: str
    audio_pcm_sha256: str
    title: str
    artist: str
    duration_frames: int
    source_path: Path
    normalized_path: Path
    chart_path: Path | None = None
    cover_path: Path | None = None
    status: SongStatus = SongStatus.IMPORTING
    analysis_version: str | None = None
    created_at: str = ""
    updated_at: str = ""
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class InputEvent:
    session_generation: int
    sequence: int
    physical_key: str
    action: InputAction
    host_time_ns: int
    midi_pitch: int | None = None
    key_index: int | None = None


@dataclass(frozen=True, slots=True)
class AudioTimelineSnapshot:
    session_generation: int
    state: PlaybackState
    chart_frame: int
    rendered_frame: int
    presented_frame: int
    output_latency_frames: int


@dataclass(frozen=True, slots=True)
class AudioDiagnostics:
    sample_rate: int
    block_size: int
    output_latency_seconds: float
    cpu_load: float
    xruns: int
    queue_overflows: int
    clipping_events: int
    last_error: str | None = None


@dataclass(slots=True)
class AnalysisJob:
    id: str
    song_id: str | None
    stage: AnalysisStage
    progress: float
    error_code: str | None = None
    error_detail: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class Score:
    song_id: str
    chart_revision: int
    chart_hash: str
    mode: GameMode
    difficulty: Difficulty | None
    total_score: int
    accuracy: float
    max_combo: int
    perfect_count: int
    good_count: int
    bad_count: int
    wrong_count: int
    miss_count: int
    hold_break_count: int
    calibration_frames: int = 0
    completed_at: str = ""


@dataclass(frozen=True, slots=True)
class JudgementResult:
    judgement: Judgement
    input_frame: int
    target_note_id: str | None
    delta_frames: int | None
    sounding_pitch: int | None
    score_delta: int
    metadata: dict[str, Any] = field(default_factory=dict)
