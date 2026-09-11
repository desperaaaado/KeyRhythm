from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from keyrhythm.domain.models import InputAction, InputEvent, Judgement, JudgementResult
from keyrhythm.gameplay.judgement import JudgementEngine


@dataclass(slots=True)
class GameplaySession:
    engine: JudgementEngine
    generation: int
    score: int = 0
    combo: int = 0
    max_combo: int = 0
    results: list[JudgementResult] = field(default_factory=list)

    def handle(self, event: InputEvent, mapped_frame: int) -> JudgementResult | None:
        if event.session_generation != self.generation:
            return None
        if event.action == InputAction.PRESS:
            result = self.engine.press(mapped_frame, key_index=event.key_index)
        else:
            result = self.engine.release(mapped_frame, key_index=event.key_index)
        if result is not None:
            self._record(result)
        return result

    def advance(self, frame: int) -> list[JudgementResult]:
        misses = self.engine.collect_misses(frame)
        for result in misses:
            self._record(result)
        return misses

    def _record(self, result: JudgementResult) -> None:
        self.results.append(result)
        self.score += result.score_delta
        if result.judgement in (Judgement.PERFECT, Judgement.GOOD):
            self.combo += 1
            self.max_combo = max(self.max_combo, self.combo)
        else:
            self.combo = 0

    @property
    def counts(self) -> Counter[Judgement]:
        return Counter(result.judgement for result in self.results)

    @property
    def accuracy(self) -> float:
        judged = [result for result in self.results if result.judgement != Judgement.GHOST]
        if not judged:
            return 0.0
        maximum = len(judged) * 1000
        return sum(result.score_delta for result in judged) / maximum

    def reset(self, generation: int) -> None:
        self.generation = generation
        self.score = self.combo = self.max_combo = 0
        self.results.clear()
        self.engine.reset()
