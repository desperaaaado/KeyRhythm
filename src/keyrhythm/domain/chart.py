from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from keyrhythm.config import CHART_SAMPLE_RATE
from keyrhythm.domain.models import Difficulty, GameMode


SCHEMA_VERSION = 3


class ChartValidationError(ValueError):
    pass


@dataclass(slots=True)
class AnalysisManifest:
    transcriber: str = "unknown"
    model_version: str = "unknown"
    model_hash: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChartNote:
    id: str
    start_frame: int
    duration_frames: int
    midi_pitch: int
    velocity: int = 90
    confidence: float = 1.0
    source: str = "manual"
    manually_edited: bool = False

    @property
    def end_frame(self) -> int:
        return self.start_frame + self.duration_frames


@dataclass(slots=True)
class KeyEvent:
    note_id: str
    key_index: int


@dataclass(slots=True)
class PlayableChart:
    id: str
    mode: GameMode
    difficulty: Difficulty | None
    key_count: int
    key_events: list[KeyEvent] = field(default_factory=list)
    key_pitch_map: list[int] = field(default_factory=list)
    mapping_algorithm: str = "adaptive_pitch_v1"
    collision_drop_count: int = 0

    @property
    def lane_count(self) -> int:
        """Compatibility name used by older UI code."""
        return self.key_count

    @property
    def events(self) -> list[KeyEvent]:
        """Compatibility name used by older gameplay code."""
        return self.key_events


@dataclass(slots=True)
class Chart:
    song_id: str
    audio_sha256: str
    duration_frames: int
    notes: list[ChartNote]
    charts: dict[str, PlayableChart]
    estimated_bpm: float = 120.0
    beat_frames: list[int] = field(default_factory=list)
    analysis_version: str = "2026.1"
    chart_revision: int = 1
    chart_sample_rate: int = CHART_SAMPLE_RATE
    audio_offset_frames: int = 0
    analysis_manifest: AnalysisManifest = field(default_factory=AnalysisManifest)
    edit_patches: list[dict[str, Any]] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    def note_map(self) -> dict[str, ChartNote]:
        return {note.id: note for note in self.notes}

    def validate(self) -> None:
        errors: list[str] = []
        if self.schema_version != SCHEMA_VERSION:
            errors.append(f"unsupported schema_version {self.schema_version}")
        if self.chart_sample_rate != CHART_SAMPLE_RATE:
            errors.append(f"chart_sample_rate must be {CHART_SAMPLE_RATE}")
        if self.duration_frames <= 0:
            errors.append("duration_frames must be positive")
        ids: set[str] = set()
        for note in self.notes:
            if note.id in ids:
                errors.append(f"duplicate note id: {note.id}")
            ids.add(note.id)
            if note.start_frame < 0 or note.duration_frames <= 0 or note.end_frame > self.duration_frames:
                errors.append(f"note out of bounds: {note.id}")
            if not 0 <= note.midi_pitch <= 127:
                errors.append(f"invalid MIDI pitch: {note.id}")
            if not 0 <= note.velocity <= 127:
                errors.append(f"invalid velocity: {note.id}")
            if not 0.0 <= note.confidence <= 1.0:
                errors.append(f"invalid confidence: {note.id}")
        for name, playable in self.charts.items():
            expected_counts = (17,) if playable.mode == GameMode.PIANO else (4, 6, 8)
            if playable.key_count not in expected_counts:
                errors.append(f"invalid key count: {name}")
            if len(playable.key_pitch_map) != playable.key_count:
                errors.append(f"invalid key pitch map length: {name}")
            if any(not 0 <= pitch <= 127 for pitch in playable.key_pitch_map):
                errors.append(f"invalid key pitch in {name}")
            if playable.mapping_algorithm != "adaptive_pitch_v1":
                errors.append(f"unsupported mapping algorithm: {name}")
            for event in playable.key_events:
                if event.note_id not in ids:
                    errors.append(f"missing note reference: {event.note_id}")
                if not 0 <= event.key_index < playable.key_count:
                    errors.append(f"invalid key index in {name}: {event.key_index}")
        if errors:
            raise ChartValidationError("; ".join(errors))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "song_id": self.song_id,
            "audio_sha256": self.audio_sha256,
            "analysis_version": self.analysis_version,
            "chart_revision": self.chart_revision,
            "chart_sample_rate": self.chart_sample_rate,
            "audio_offset_frames": self.audio_offset_frames,
            "duration_frames": self.duration_frames,
            "analysis_manifest": asdict(self.analysis_manifest),
            "tempo": {"estimated_bpm": self.estimated_bpm, "beat_frames": self.beat_frames},
            "notes": [asdict(note) for note in self.notes],
            "charts": {
                name: {
                    "id": playable.id,
                    "mode": playable.mode.value,
                    "difficulty": playable.difficulty.value if playable.difficulty else None,
                    "key_count": playable.key_count,
                    "key_events": [asdict(event) for event in playable.key_events],
                    "key_pitch_map": playable.key_pitch_map,
                    "mapping_algorithm": playable.mapping_algorithm,
                    "collision_drop_count": playable.collision_drop_count,
                }
                for name, playable in self.charts.items()
            },
            "edit_patches": self.edit_patches,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Chart":
        if raw.get("schema_version", 1) == 1:
            raw = migrate_v1_to_v2(raw)
        if raw.get("schema_version") == 2:
            raw = migrate_v2_to_v3(raw)
        tempo = raw.get("tempo", {})
        charts: dict[str, PlayableChart] = {}
        for name, value in raw.get("charts", {}).items():
            inferred_mode = GameMode.PIANO if name == "piano" else GameMode.LANE
            difficulty_value = value.get("difficulty")
            charts[name] = PlayableChart(
                id=value.get("id", name),
                mode=GameMode(value.get("mode", inferred_mode.value)),
                difficulty=Difficulty(difficulty_value) if difficulty_value else None,
                key_count=int(value["key_count"]),
                key_events=[KeyEvent(**event) for event in value.get("key_events", [])],
                key_pitch_map=[int(pitch) for pitch in value.get("key_pitch_map", [])],
                mapping_algorithm=value.get("mapping_algorithm", "adaptive_pitch_v1"),
                collision_drop_count=int(value.get("collision_drop_count", 0)),
            )
        chart = cls(
            schema_version=int(raw["schema_version"]),
            song_id=raw["song_id"],
            audio_sha256=raw["audio_sha256"],
            analysis_version=raw.get("analysis_version", "unknown"),
            chart_revision=int(raw.get("chart_revision", 1)),
            chart_sample_rate=int(raw.get("chart_sample_rate", CHART_SAMPLE_RATE)),
            audio_offset_frames=int(raw.get("audio_offset_frames", 0)),
            duration_frames=int(raw["duration_frames"]),
            estimated_bpm=float(tempo.get("estimated_bpm", 120.0)),
            beat_frames=[int(value) for value in tempo.get("beat_frames", [])],
            notes=[ChartNote(**value) for value in raw.get("notes", [])],
            charts=charts,
            analysis_manifest=AnalysisManifest(**raw.get("analysis_manifest", {})),
            edit_patches=list(raw.get("edit_patches", [])),
        )
        chart.validate()
        return chart


def migrate_v1_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
    migrated = json.loads(json.dumps(raw))
    rate = CHART_SAMPLE_RATE
    migrated["schema_version"] = 2
    migrated["chart_revision"] = int(migrated.get("chart_revision", 1))
    migrated["chart_sample_rate"] = rate
    migrated["audio_offset_frames"] = round(migrated.pop("audio_offset_ms", 0) * rate / 1000)
    migrated["duration_frames"] = round(migrated.pop("duration_ms") * rate / 1000)
    tempo = migrated.setdefault("tempo", {})
    tempo["beat_frames"] = [round(value * rate / 1000) for value in tempo.pop("beats_ms", [])]
    migrated["analysis_manifest"] = migrated.get("analysis_manifest", {})
    migrated["edit_patches"] = migrated.get("edit_patches", [])
    for note in migrated.get("notes", []):
        note["start_frame"] = round(note.pop("start_ms") * rate / 1000)
        note["duration_frames"] = max(1, round(note.pop("duration_ms") * rate / 1000))
    for name, playable in migrated.get("charts", {}).items():
        if name == "piano":
            playable.update({"id": name, "mode": "piano", "difficulty": None, "lane_count": None})
        else:
            parts = name.split("_")
            lanes = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 4
            difficulty = parts[2] if len(parts) > 2 else "easy"
            playable.update({"id": name, "mode": "lane", "difficulty": difficulty, "lane_count": lanes})
    return migrated


def migrate_v2_to_v3(raw: dict[str, Any]) -> dict[str, Any]:
    """Regenerate deterministic adaptive key maps from the source notes."""
    migrated = json.loads(json.dumps(raw))
    notes = [ChartNote(**value) for value in migrated.get("notes", [])]
    # Late import avoids a module cycle while keeping migration in one place.
    from keyrhythm.domain.difficulty import generate_playable_charts

    charts = generate_playable_charts(notes)
    migrated["schema_version"] = 3
    migrated["chart_revision"] = int(migrated.get("chart_revision", 1)) + 1
    migrated["charts"] = {
        name: {
            "id": playable.id,
            "mode": playable.mode.value,
            "difficulty": playable.difficulty.value if playable.difficulty else None,
            "key_count": playable.key_count,
            "key_events": [asdict(event) for event in playable.key_events],
            "key_pitch_map": playable.key_pitch_map,
            "mapping_algorithm": playable.mapping_algorithm,
            "collision_drop_count": playable.collision_drop_count,
        }
        for name, playable in charts.items()
    }
    migrated.setdefault("edit_patches", []).append({
        "revision": migrated["chart_revision"],
        "operation": "schema_v2_to_v3_adaptive_mapping",
    })
    return migrated


def load_chart(path: Path) -> Chart:
    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    source_version = int(raw.get("schema_version", 1))
    chart = Chart.from_dict(raw)
    if source_version < SCHEMA_VERSION:
        backup_path = path.with_name(f"chart.backup-v{source_version}.json")
        if not backup_path.exists():
            shutil.copy2(path, backup_path)
        save_chart_atomic(chart, path, backup=False)
    return chart


def save_chart_atomic(chart: Chart, path: Path, *, backup: bool = True) -> None:
    chart.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    backup_path = path.with_name("chart.backup.json")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(chart.to_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    Chart.from_dict(json.loads(temporary.read_text(encoding="utf-8")))
    if backup and path.exists():
        shutil.copy2(path, backup_path)
    os.replace(temporary, path)


def next_note_id(notes: Iterable[ChartNote]) -> str:
    numeric = []
    for note in notes:
        try:
            numeric.append(int(note.id.rsplit("-", 1)[-1]))
        except ValueError:
            continue
    return f"n-{max(numeric, default=0) + 1:06d}"
