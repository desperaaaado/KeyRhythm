from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QImage, QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from keyrhythm.domain.chart import Chart, ChartNote, save_chart_atomic
from keyrhythm.domain.difficulty import generate_playable_charts
from keyrhythm.domain.models import AudioTimelineSnapshot, PlaybackState
from keyrhythm.gameplay.judgement import TimingWindows
from keyrhythm.ui.key_layout import bindings_for, key_index_for


class FakeAudioEngine:
    def __init__(self, **_kwargs):
        self.session_generation = 1
        self.state = PlaybackState.READY
        self.frame = 0
        self.inputs = []

    def load_song(self, _path):
        pass

    def set_bus_volume(self, *_args):
        pass

    def play(self):
        self.state = PlaybackState.PLAYING

    def pause(self):
        self.state = PlaybackState.PAUSED

    def resume(self):
        self.state = PlaybackState.PLAYING

    def seek(self, frame):
        self.frame = frame
        self.session_generation += 1

    def map_input_time(self, _host_time_ns):
        return self.frame

    def submit_input(self, event):
        self.inputs.append(event)
        return True

    def get_timeline_snapshot(self):
        return AudioTimelineSnapshot(
            self.session_generation, self.state, self.frame, self.frame, self.frame, 0
        )

    def close(self):
        self.state = PlaybackState.STOPPED


class FakeRepository:
    def __init__(self):
        self.scores = []

    def save_score(self, score):
        self.scores.append(score)


class GameUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.environment = patch.dict(os.environ, {"KEYRHYTHM_DATA_DIR": str(root)})
        self.environment.start()
        notes = [
            ChartNote("n-1", 48_000, 12_000, 48, confidence=1.0),
            ChartNote("n-2", 72_000, 12_000, 60, confidence=1.0),
            ChartNote("n-3", 96_000, 12_000, 72, confidence=1.0),
        ]
        chart = Chart("song", "abc", 144_000, notes, generate_playable_charts(notes))
        chart_path = root / "chart.json"
        save_chart_atomic(chart, chart_path, backup=False)
        audio_path = root / "song.wav"
        audio_path.touch()
        self.song = SimpleNamespace(
            id="song", title="UI Test", artist="KeyRhythm", chart_path=chart_path,
            normalized_path=audio_path, cover_path=None,
        )

    def tearDown(self) -> None:
        self.environment.stop()
        self.directory.cleanup()

    def _window(self):
        from keyrhythm.ui import game_window

        patcher = patch.object(game_window, "AudioEngine", FakeAudioEngine)
        patcher.start()
        self.addCleanup(patcher.stop)
        window = game_window.GameWindow(self.song, FakeRepository())
        window.resize(1280, 720)
        window.show()
        self.app.processEvents()
        window.chart_selector.setCurrentIndex(window.chart_selector.findData("lane_4_easy"))
        return window

    def test_key_layout_is_single_source_for_all_modes(self) -> None:
        for count in (4, 6, 8, 17):
            bindings = bindings_for(count)
            self.assertEqual(len(bindings), count)
            for index, binding in enumerate(bindings):
                self.assertEqual(key_index_for(count, int(binding.qt_key)), index)

    def test_press_release_and_perfect_feedback(self) -> None:
        window = self._window()
        playable = window.canvas.playable
        event = playable.key_events[0]
        window.audio.frame = 48_000
        key = bindings_for(playable.key_count)[event.key_index].qt_key
        window.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier))
        self.assertIn(event.key_index, window.canvas.pressed_keys)
        self.assertEqual(window.canvas.effects[-1].result.judgement.value, "perfect")
        window.keyReleaseEvent(QKeyEvent(QEvent.Type.KeyRelease, key, Qt.KeyboardModifier.NoModifier))
        self.assertNotIn(event.key_index, window.canvas.pressed_keys)
        window.close()

    def test_pause_button_does_not_resume_from_internal_focus_change(self) -> None:
        window = self._window()
        window.activateWindow()
        window.setFocus()
        self.app.processEvents()

        QTest.mouseClick(window.pause_button, Qt.MouseButton.LeftButton)
        self.app.processEvents()

        self.assertEqual(window.audio.state, PlaybackState.PAUSED)
        self.assertFalse(window.overlay.isHidden())
        self.assertEqual(window.pause_button.text(), "继续")
        window.close()

    def test_switching_difficulty_restarts_song_and_session(self) -> None:
        window = self._window()
        window.audio.frame = 96_000
        window.session.score = 5000
        window.session.combo = 5
        window.active_pitches[1] = 60
        window.progress.setValue(750)

        target_index = window.chart_selector.findData("lane_6_normal")
        window.chart_selector.setCurrentIndex(target_index)
        self.app.processEvents()

        self.assertEqual(window.audio.frame, 0)
        self.assertEqual(window.audio.state, PlaybackState.PLAYING)
        self.assertEqual(window.canvas.playable.id, "lane_6_normal")
        self.assertEqual(window.session.generation, window.audio.session_generation)
        self.assertEqual(window.session.score, 0)
        self.assertEqual(window.session.combo, 0)
        self.assertFalse(window.active_pitches)
        self.assertEqual(window.progress.value(), 0)
        self.assertEqual(window.score_label.text(), "SCORE 0000000")
        window.close()

    def test_tick_routes_miss_to_canvas_and_pause_clears_state(self) -> None:
        window = self._window()
        window.audio.frame = 48_000 + TimingWindows().bad_frames + 1
        window._tick()
        self.assertEqual(window.canvas.effects[-1].result.judgement.value, "miss")
        window.canvas.pressed_keys.add(0)
        window.toggle_pause()
        self.assertFalse(window.overlay.isHidden())
        window.canvas.clear_feedback()
        self.assertFalse(window.canvas.pressed_keys)
        window.close()

    def test_canvas_renders_at_supported_sizes(self) -> None:
        window = self._window()
        for width, height in ((900, 650), (1280, 720), (1920, 1080)):
            window.resize(width, height)
            self.app.processEvents()
            image = QImage(window.size(), QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            started = time.perf_counter()
            window.render(image)
            self.assertFalse(image.isNull())
            self.assertLess(time.perf_counter() - started, 0.25)
        window.close()


if __name__ == "__main__":
    unittest.main()
