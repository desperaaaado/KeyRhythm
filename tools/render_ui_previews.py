from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication

from keyrhythm.config import AppPaths
from keyrhythm.domain.models import AudioTimelineSnapshot, Judgement, JudgementResult, PlaybackState
from keyrhythm.library import Database, SongRepository
from keyrhythm.library.presets import ensure_builtin_song
from keyrhythm.ui.editor_window import EditorWindow
from keyrhythm.ui.main_window import MainWindow
from keyrhythm.ui.settings_dialog import SettingsDialog
from keyrhythm.ui.theme import apply_theme
import keyrhythm.ui.game_window as game_module


class PreviewAudioEngine:
    def __init__(self, **_kwargs):
        self.session_generation = 1
        self.state = PlaybackState.READY
        self.frame = 48_000

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

    def map_input_time(self, _value):
        return self.frame

    def submit_input(self, _event):
        return True

    def get_timeline_snapshot(self):
        return AudioTimelineSnapshot(self.session_generation, self.state, self.frame, self.frame, self.frame, 0)

    def close(self):
        self.state = PlaybackState.STOPPED


def save_widget(widget, path: Path, size: tuple[int, int], application: QApplication) -> None:
    widget.resize(*size)
    widget.show()
    application.processEvents()
    widget.grab().save(str(path))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=PROJECT / ".keyrhythm-dev" / "ui-previews")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("KEYRHYTHM_DATA_DIR", str(PROJECT / ".keyrhythm-dev" / "ui-preview-data"))

    application = QApplication([])
    # The offscreen QPA plugin does not enumerate Windows fonts. Loading the
    # same system fonts explicitly makes automated previews representative of
    # the normal Windows platform plugin without bundling font files.
    for font_path in (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/msyh.ttc")):
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    apply_theme(application)
    main_window = MainWindow()
    save_widget(main_window, args.output / "library-1280x720.png", (1280, 720), application)
    song = main_window.selected_song()
    if not song:
        return 2

    game_module.AudioEngine = PreviewAudioEngine
    game = game_module.GameWindow(song, main_window.repository)
    game.chart_selector.setCurrentIndex(game.chart_selector.findData("lane_8_hard"))
    game.canvas.current_frame = 48_000
    event = game.canvas.playable.key_events[0]
    game.canvas.set_key_pressed(event.key_index, True)
    game.canvas.apply_judgement(JudgementResult(
        judgement=Judgement.PERFECT,
        input_frame=48_000,
        target_note_id=event.note_id,
        delta_frames=-240,
        sounding_pitch=60,
        score_delta=1000,
        metadata={"key_index": event.key_index},
    ), 24)
    save_widget(game, args.output / "game-1280x720.png", (1280, 720), application)

    editor = EditorWindow(song, main_window.repository)
    save_widget(editor, args.output / "editor-1280x720.png", (1280, 720), application)
    settings = SettingsDialog(AppPaths.discover().settings)
    save_widget(settings, args.output / "settings-700x760.png", (700, 760), application)

    for widget in (settings, editor, game, main_window):
        widget.close()
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
