from __future__ import annotations

from dataclasses import dataclass

from keyrhythm.config import CHART_SAMPLE_RATE
from keyrhythm.domain.chart import ChartNote, PlayableChart
from keyrhythm.domain.models import Judgement, JudgementResult


@dataclass(frozen=True, slots=True)
class TimingWindows:
    perfect_frames: int = round(0.045 * CHART_SAMPLE_RATE)
    good_frames: int = round(0.090 * CHART_SAMPLE_RATE)
    bad_frames: int = round(0.150 * CHART_SAMPLE_RATE)


@dataclass(slots=True)
class _TargetState:
    note: ChartNote
    key_index: int
    consumed: bool = False
    active: bool = False
    released: bool = False


SCORES = {
    Judgement.PERFECT: 1000,
    Judgement.GOOD: 700,
    Judgement.BAD: 300,
    Judgement.WRONG: 0,
    Judgement.MISS: 0,
    Judgement.GHOST: 0,
    Judgement.HOLD_BREAK: 0,
}


class JudgementEngine:
    def __init__(self, notes: list[ChartNote], playable: PlayableChart, windows: TimingWindows | None = None):
        self.windows = windows or TimingWindows()
        self.key_pitch_map = playable.key_pitch_map
        by_id = {note.id: note for note in notes}
        self.targets = [_TargetState(by_id[event.note_id], event.key_index) for event in playable.key_events]
        self.targets.sort(key=lambda target: (target.note.start_frame, target.note.midi_pitch))

    @staticmethod
    def _matches(target: _TargetState, key_index: int | None) -> bool:
        return key_index == target.key_index

    def press(self, input_frame: int, *, key_index: int | None = None) -> JudgementResult:
        candidates = [
            target
            for target in self.targets
            if not target.consumed and abs(input_frame - target.note.start_frame) <= self.windows.bad_frames
        ]
        correct = [target for target in candidates if self._matches(target, key_index)]
        if correct:
            target = min(correct, key=lambda value: (abs(input_frame - value.note.start_frame), value.note.start_frame))
            delta = input_frame - target.note.start_frame
            judgement = self._timing_judgement(abs(delta))
            target.consumed = True
            target.active = True
            return self._result(judgement, input_frame, target, delta, target.note.midi_pitch)
        if candidates:
            target = min(candidates, key=lambda value: (abs(input_frame - value.note.start_frame), value.note.start_frame))
            target.consumed = True
            delta = input_frame - target.note.start_frame
            sounding = self._sounding_pitch(key_index)
            return self._result(Judgement.WRONG, input_frame, target, delta, sounding)
        return JudgementResult(
            judgement=Judgement.GHOST,
            input_frame=input_frame,
            target_note_id=None,
            delta_frames=None,
            sounding_pitch=self._sounding_pitch(key_index),
            score_delta=0,
        )

    def release(self, input_frame: int, *, key_index: int | None = None) -> JudgementResult | None:
        active = [target for target in self.targets if target.active and not target.released and self._matches(target, key_index)]
        if not active:
            return None
        target = min(active, key=lambda value: value.note.end_frame)
        target.released = True
        target.active = False
        early_by = target.note.end_frame - input_frame
        if early_by > self.windows.bad_frames:
            return self._result(Judgement.HOLD_BREAK, input_frame, target, -early_by, target.note.midi_pitch)
        return None

    def collect_misses(self, current_frame: int) -> list[JudgementResult]:
        results: list[JudgementResult] = []
        for target in self.targets:
            if not target.consumed and current_frame > target.note.start_frame + self.windows.bad_frames:
                target.consumed = True
                results.append(self._result(Judgement.MISS, current_frame, target, None, None))
        return results

    def reset(self) -> None:
        for target in self.targets:
            target.consumed = False
            target.active = False
            target.released = False

    def _timing_judgement(self, absolute_delta: int) -> Judgement:
        if absolute_delta <= self.windows.perfect_frames:
            return Judgement.PERFECT
        if absolute_delta <= self.windows.good_frames:
            return Judgement.GOOD
        return Judgement.BAD

    def _sounding_pitch(self, key_index: int | None) -> int | None:
        if key_index is None or not 0 <= key_index < len(self.key_pitch_map):
            return None
        return self.key_pitch_map[key_index]

    @staticmethod
    def _result(
        judgement: Judgement,
        input_frame: int,
        target: _TargetState,
        delta: int | None,
        sounding_pitch: int | None,
    ) -> JudgementResult:
        return JudgementResult(
            judgement=judgement,
            input_frame=input_frame,
            target_note_id=target.note.id,
            delta_frames=delta,
            sounding_pitch=sounding_pitch,
            score_delta=SCORES[judgement],
            metadata={"key_index": target.key_index},
        )
