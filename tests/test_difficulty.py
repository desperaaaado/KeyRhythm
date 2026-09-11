from __future__ import annotations

import unittest

from keyrhythm.domain.chart import ChartNote
from keyrhythm.domain.difficulty import fold_pitch, generate_playable_charts


class DifficultyTests(unittest.TestCase):
    def test_generates_all_modes_with_valid_lanes(self) -> None:
        notes = [ChartNote(f"n-{index:06d}", index * 12_000, 6_000, 48 + index, confidence=0.9) for index in range(1, 20)]
        charts = generate_playable_charts(notes)
        self.assertEqual(set(charts), {"piano", "lane_4_easy", "lane_6_normal", "lane_8_hard"})
        for name in ("lane_4_easy", "lane_6_normal", "lane_8_hard"):
            chart = charts[name]
            self.assertTrue(chart.events)
            self.assertTrue(all(0 <= event.key_index < chart.key_count for event in chart.key_events))
            self.assertEqual(len(chart.key_pitch_map), chart.key_count)

    def test_unique_pitches_do_not_merge_when_keys_are_available(self) -> None:
        notes = [ChartNote(f"n-{index}", index * 20_000, 4_000, pitch) for index, pitch in enumerate((48, 55, 64, 72))]
        chart = generate_playable_charts(notes)["lane_4_easy"]
        indices = [event.key_index for event in chart.key_events]
        self.assertEqual(indices, [0, 1, 2, 3])

    def test_more_pitches_than_keys_are_monotonic_and_fill_endpoints(self) -> None:
        notes = [ChartNote(f"n-{index}", index * 20_000, 4_000, 40 + index) for index in range(9)]
        chart = generate_playable_charts(notes)["lane_4_easy"]
        indices = [event.key_index for event in chart.key_events]
        self.assertEqual(indices[0], 0)
        self.assertEqual(indices[-1], 3)
        self.assertEqual(sorted(indices), indices)
        self.assertEqual(set(indices), {0, 1, 2, 3})

    def test_single_pitch_is_centered(self) -> None:
        notes = [ChartNote("n-1", 0, 4_000, 60)]
        chart = generate_playable_charts(notes)["piano"]
        self.assertEqual(chart.key_events[0].key_index, 8)

    def test_same_pitch_always_uses_same_key(self) -> None:
        notes = [ChartNote(f"n-{index}", index * 20_000, 4_000, pitch) for index, pitch in enumerate((48, 60, 48, 72, 60))]
        chart = generate_playable_charts(notes)["piano"]
        note_map = {note.id: note for note in notes}
        by_pitch: dict[int, set[int]] = {}
        for event in chart.key_events:
            by_pitch.setdefault(note_map[event.note_id].midi_pitch, set()).add(event.key_index)
        self.assertTrue(all(len(indices) == 1 for indices in by_pitch.values()))

    def test_simultaneous_collision_keeps_stronger_note(self) -> None:
        notes = [
            ChartNote("low", 0, 4_000, 40, confidence=0.7),
            ChartNote("strong", 0, 4_000, 41, confidence=0.95),
        ]
        notes.extend(
            ChartNote(f"n-{index}", index * 20_000, 4_000, 40 + index, confidence=0.9)
            for index in range(2, 18)
        )
        chart = generate_playable_charts(notes)["lane_8_hard"]
        event_ids = {event.note_id for event in chart.key_events}
        self.assertEqual(chart.collision_drop_count, 1)
        self.assertIn("strong", event_ids)
        self.assertNotIn("low", event_ids)

    def test_pitch_folding(self) -> None:
        self.assertEqual(fold_pitch(36), 48)
        self.assertEqual(fold_pitch(84), 60)


if __name__ == "__main__":
    unittest.main()
