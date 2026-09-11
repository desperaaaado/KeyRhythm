from __future__ import annotations

from dataclasses import dataclass

from keyrhythm.config import CHART_SAMPLE_RATE
from keyrhythm.domain.chart import ChartNote, KeyEvent, PlayableChart
from keyrhythm.domain.models import Difficulty, GameMode


@dataclass(frozen=True, slots=True)
class DifficultyPolicy:
    lane_count: int
    difficulty: Difficulty
    minimum_confidence: float
    minimum_gap_frames: int
    allow_chords: bool


POLICIES = {
    "lane_4_easy": DifficultyPolicy(4, Difficulty.EASY, 0.65, CHART_SAMPLE_RATE // 4, False),
    "lane_6_normal": DifficultyPolicy(6, Difficulty.NORMAL, 0.45, CHART_SAMPLE_RATE // 8, False),
    "lane_8_hard": DifficultyPolicy(8, Difficulty.HARD, 0.25, CHART_SAMPLE_RATE // 16, True),
}

PIANO_KEY_COUNT = 17
MAPPING_ALGORITHM = "adaptive_pitch_v1"
CHORD_WINDOW_FRAMES = CHART_SAMPLE_RATE // 100


def fold_pitch(pitch: int, low: int = 48, high: int = 71) -> int:
    while pitch < low:
        pitch += 12
    while pitch > high:
        pitch -= 12
    return max(low, min(high, pitch))


def _select_notes(notes: list[ChartNote], policy: DifficultyPolicy) -> list[ChartNote]:
    selected: list[ChartNote] = []
    for note in sorted(notes, key=lambda item: (item.start_frame, -item.confidence, item.midi_pitch)):
        if note.confidence < policy.minimum_confidence:
            continue
        recent: list[ChartNote] = []
        for item in reversed(selected):
            if note.start_frame - item.start_frame >= policy.minimum_gap_frames:
                break
            recent.append(item)
        if recent and not policy.allow_chords:
            incumbent = recent[0]
            if note.confidence > incumbent.confidence:
                selected.remove(incumbent)
                selected.append(note)
            continue
        if policy.allow_chords:
            simultaneous = [item for item in recent if note.start_frame - item.start_frame < 480]
            if len(simultaneous) >= 2:
                continue
        selected.append(note)
    return sorted(selected, key=lambda item: (item.start_frame, item.midi_pitch))


def _pitch_key_indices(notes: list[ChartNote], key_count: int) -> dict[int, int]:
    pitches = sorted({note.midi_pitch for note in notes})
    if not pitches:
        return {}
    if len(pitches) == 1:
        return {pitches[0]: key_count // 2}
    denominator = len(pitches) - 1
    return {
        pitch: int(index * (key_count - 1) / denominator + 0.5)
        for index, pitch in enumerate(pitches)
    }


def _representative_pitches(pitch_keys: dict[int, int], key_count: int) -> list[int]:
    if not pitch_keys:
        return [60 for _ in range(key_count)]
    if len(pitch_keys) == 1:
        pitch = next(iter(pitch_keys))
        center = key_count // 2
        return [max(0, min(127, pitch + index - center)) for index in range(key_count)]
    grouped: dict[int, list[int]] = {index: [] for index in range(key_count)}
    for pitch, key_index in pitch_keys.items():
        grouped[key_index].append(pitch)
    occupied = sorted(index for index, values in grouped.items() if values)
    representatives: list[int] = []
    for index in range(key_count):
        values = grouped[index]
        if values:
            representatives.append(round(sum(values) / len(values)))
            continue
        left = max((value for value in occupied if value < index), default=occupied[0])
        right = min((value for value in occupied if value > index), default=occupied[-1])
        left_pitch = round(sum(grouped[left]) / len(grouped[left]))
        right_pitch = round(sum(grouped[right]) / len(grouped[right]))
        if left == right:
            representatives.append(left_pitch)
        else:
            representatives.append(round(left_pitch + (right_pitch - left_pitch) * (index - left) / (right - left)))
    return [max(0, min(127, pitch)) for pitch in representatives]


def _map_keys(notes: list[ChartNote], key_count: int) -> tuple[list[KeyEvent], list[int], int]:
    pitch_keys = _pitch_key_indices(notes, key_count)
    events: list[KeyEvent] = []
    dropped = 0
    ordered = sorted(notes, key=lambda note: (note.start_frame, note.midi_pitch, -note.confidence))
    group: list[ChartNote] = []

    def commit(current: list[ChartNote]) -> None:
        nonlocal dropped
        by_key: dict[int, ChartNote] = {}
        for note in current:
            key_index = pitch_keys[note.midi_pitch]
            incumbent = by_key.get(key_index)
            if incumbent is None or (note.confidence, note.velocity) > (incumbent.confidence, incumbent.velocity):
                if incumbent is not None:
                    dropped += 1
                by_key[key_index] = note
            else:
                dropped += 1
        for key_index, note in sorted(by_key.items()):
            events.append(KeyEvent(note_id=note.id, key_index=key_index))

    for note in ordered:
        if group and note.start_frame - group[0].start_frame > CHORD_WINDOW_FRAMES:
            commit(group)
            group = []
        group.append(note)
    if group:
        commit(group)
    order = {note.id: (note.start_frame, note.midi_pitch) for note in ordered}
    events.sort(key=lambda event: order[event.note_id])
    return events, _representative_pitches(pitch_keys, key_count), dropped


def generate_playable_charts(notes: list[ChartNote]) -> dict[str, PlayableChart]:
    piano_events, piano_pitches, piano_dropped = _map_keys(notes, PIANO_KEY_COUNT)
    charts: dict[str, PlayableChart] = {
        "piano": PlayableChart(
            id="piano",
            mode=GameMode.PIANO,
            difficulty=None,
            key_count=PIANO_KEY_COUNT,
            key_events=piano_events,
            key_pitch_map=piano_pitches,
            mapping_algorithm=MAPPING_ALGORITHM,
            collision_drop_count=piano_dropped,
        )
    }
    for name, policy in POLICIES.items():
        selected = _select_notes(notes, policy)
        events, pitches, dropped = _map_keys(selected, policy.lane_count)
        charts[name] = PlayableChart(
            id=name,
            mode=GameMode.LANE,
            difficulty=policy.difficulty,
            key_count=policy.lane_count,
            key_events=events,
            key_pitch_map=pitches,
            mapping_algorithm=MAPPING_ALGORITHM,
            collision_drop_count=dropped,
        )
    return charts


def is_playable(notes: list[ChartNote], charts: dict[str, PlayableChart]) -> bool:
    if not notes:
        return False
    if sum(note.confidence >= 0.5 for note in notes) / len(notes) < 0.5:
        return False
    return all(bool(chart.key_events) for chart in charts.values() if chart.mode == GameMode.LANE)
