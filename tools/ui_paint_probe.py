from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QImage
from PySide6.QtWidgets import QApplication

from keyrhythm.domain.chart import Chart, ChartNote, KeyEvent, PlayableChart
from keyrhythm.domain.models import Difficulty, GameMode
from keyrhythm.ui.game_window import NoteCanvas


def main() -> int:
    application = QApplication([])
    for font_path in (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/msyh.ttc")):
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    notes = [
        ChartNote(f"n-{index:06d}", index * 2_880, 1_920, 48 + index % 25, confidence=0.9)
        for index in range(5_000)
    ]
    playable = PlayableChart(
        "lane_8_hard", GameMode.LANE, Difficulty.HARD, 8,
        [KeyEvent(note.id, note.midi_pitch % 8) for note in notes],
        [48, 52, 55, 59, 62, 65, 69, 72],
    )
    chart = Chart("probe", "probe", notes[-1].end_frame + 48_000, notes, {playable.id: playable})
    canvas = NoteCanvas(chart)
    canvas.resize(1280, 600)
    canvas.set_playable(playable)
    image = QImage(canvas.size(), QImage.Format.Format_ARGB32)
    durations: list[float] = []
    for index in range(180):
        canvas.current_frame = 4_000_000 + index * 800
        image.fill(Qt.GlobalColor.transparent)
        started = time.perf_counter()
        canvas.render(image)
        durations.append((time.perf_counter() - started) * 1000)
    ordered = sorted(durations)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    report = {
        "frames": len(durations),
        "chart_notes": len(notes),
        "mean_paint_ms": sum(durations) / len(durations),
        "p95_paint_ms": p95,
        "gate_ms": 8.0,
        "passes": p95 < 8.0,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["passes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
