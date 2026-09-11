from __future__ import annotations

import dataclasses
import hashlib
import math
import time
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QKeyEvent, QLinearGradient, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from keyrhythm.audio import AudioEngine, AudioUnavailableError
from keyrhythm.config import AppPaths, CHART_SAMPLE_RATE
from keyrhythm.domain.chart import Chart, ChartNote, PlayableChart, load_chart
from keyrhythm.domain.models import AudioBus, InputAction, InputEvent, Judgement, JudgementResult, Score
from keyrhythm.gameplay import GameplaySession, JudgementEngine
from keyrhythm.settings import Settings
from keyrhythm.ui.key_layout import bindings_for, key_index_for, midi_note_name


JUDGEMENT_STYLE = {
    Judgement.PERFECT: ("PERFECT", QColor("#E8FDFF"), QColor("#3DEBFF")),
    Judgement.GOOD: ("GOOD", QColor("#B8FFD9"), QColor("#41F59B")),
    Judgement.BAD: ("BAD", QColor("#FFE7A3"), QColor("#FFB84D")),
    Judgement.WRONG: ("WRONG", QColor("#FFD3FF"), QColor("#F04BFF")),
    Judgement.MISS: ("MISS", QColor("#FFD0D8"), QColor("#FF476F")),
    Judgement.HOLD_BREAK: ("HOLD BREAK", QColor("#FFE0C2"), QColor("#FF784D")),
    Judgement.GHOST: ("空击", QColor("#CAD1E5"), QColor("#8B77B8")),
}


def _blur_pixmap(source: QPixmap) -> QPixmap:
    if source.isNull():
        return source
    result = QPixmap(source.size())
    result.fill(Qt.GlobalColor.transparent)
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(source)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(26)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    painter = QPainter(result)
    scene.render(painter, QRectF(result.rect()), QRectF(source.rect()))
    painter.end()
    return result


@dataclass(slots=True)
class VisualEffect:
    result: JudgementResult
    key_index: int | None
    started_at: float
    combo: int


class NoteCanvas(QWidget):
    MAX_EFFECTS = 64

    def __init__(self, chart: Chart, parent=None):
        super().__init__(parent)
        self.chart = chart
        self.playable: PlayableChart | None = None
        self.current_frame = 0
        self.pressed_keys: set[int] = set()
        self.effects: list[VisualEffect] = []
        self.note_states: dict[str, tuple[Judgement, float]] = {}
        self.render_entries: list[tuple[ChartNote, int]] = []
        self.render_starts: list[int] = []
        self.pitch_labels: list[str] = []
        self.maximum_duration = CHART_SAMPLE_RATE
        self.setMinimumHeight(470)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_playable(self, playable: PlayableChart) -> None:
        self.playable = playable
        note_map = self.chart.note_map()
        self.render_entries = sorted(
            ((note_map[event.note_id], event.key_index) for event in playable.key_events),
            key=lambda value: (value[0].start_frame, value[0].midi_pitch),
        )
        self.render_starts = [note.start_frame for note, _key_index in self.render_entries]
        self.maximum_duration = max((note.duration_frames for note, _key_index in self.render_entries), default=CHART_SAMPLE_RATE)
        self.pitch_labels = [self._build_pitch_label(index) for index in range(playable.key_count)]
        self.clear_feedback()

    def set_key_pressed(self, key_index: int, pressed: bool) -> None:
        if pressed:
            self.pressed_keys.add(key_index)
        else:
            self.pressed_keys.discard(key_index)
        self.update()

    def apply_judgement(self, result: JudgementResult, combo: int) -> None:
        now = time.monotonic()
        key_index = result.metadata.get("key_index")
        if result.target_note_id:
            self.note_states[result.target_note_id] = (result.judgement, now)
        self.effects.append(VisualEffect(result, key_index, now, combo))
        if len(self.effects) > self.MAX_EFFECTS:
            del self.effects[:-self.MAX_EFFECTS]
        self.update()

    def clear_feedback(self) -> None:
        self.pressed_keys.clear()
        self.effects.clear()
        self.note_states.clear()
        self.update()

    def _build_pitch_label(self, key_index: int) -> str:
        assert self.playable is not None
        note_map = self.chart.note_map()
        pitches = sorted({
            note_map[event.note_id].midi_pitch
            for event in self.playable.key_events
            if event.key_index == key_index and event.note_id in note_map
        })
        if not pitches:
            return midi_note_name(self.playable.key_pitch_map[key_index])
        if len(pitches) == 1:
            return midi_note_name(pitches[0])
        return f"{midi_note_name(pitches[0])}–{midi_note_name(pitches[-1])}"

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background = QLinearGradient(0, 0, 0, self.height())
        background.setColorAt(0, QColor("#080B18"))
        background.setColorAt(1, QColor("#11152A"))
        painter.fillRect(self.rect(), background)
        if not self.playable:
            return

        now = time.monotonic()
        self.effects = [effect for effect in self.effects if now - effect.started_at < 0.72]
        note_map = self.chart.note_map()
        self.note_states = {
            note_id: state for note_id, state in self.note_states.items()
            if now - state[1] < 0.42 or (
                note_id in note_map
                and state[0] in (Judgement.PERFECT, Judgement.GOOD, Judgement.BAD)
                and note_map[note_id].duration_frames >= CHART_SAMPLE_RATE // 4
                and self.current_frame <= note_map[note_id].end_frame
            )
        }
        key_count = self.playable.key_count
        lane_width = self.width() / key_count
        receptor_height = 72
        target_y = self.height() - receptor_height - 10

        for key_index in range(key_count):
            x = round(key_index * lane_width)
            lane_color = QColor("#16203A") if key_index % 2 == 0 else QColor("#10182D")
            if key_index in self.pressed_keys:
                lane_color = QColor("#163E55")
            painter.fillRect(x, 0, math.ceil(lane_width), target_y, lane_color)
            if key_index in self.pressed_keys:
                glow = QLinearGradient(0, target_y - 180, 0, target_y)
                glow.setColorAt(0, QColor(61, 235, 255, 0))
                glow.setColorAt(1, QColor(61, 235, 255, 105))
                painter.fillRect(x + 2, target_y - 180, max(1, round(lane_width - 4)), 180, glow)

        painter.setPen(QPen(QColor("#2A3656"), 1))
        for lane in range(1, key_count):
            x = round(lane * lane_width)
            painter.drawLine(x, 0, x, self.height())

        lookahead = CHART_SAMPLE_RATE * 3
        visible_start = bisect_left(self.render_starts, self.current_frame - max(CHART_SAMPLE_RATE, self.maximum_duration))
        visible_end = bisect_right(self.render_starts, self.current_frame + lookahead)
        for note, key_index in self.render_entries[visible_start:visible_end]:
            state = self.note_states.get(note.id)
            is_active_hold = False
            if state and state[0] not in (Judgement.MISS, Judgement.HOLD_BREAK):
                is_active_hold = note.duration_frames >= CHART_SAMPLE_RATE // 4 and self.current_frame <= note.end_frame
                if not is_active_hold:
                    continue
            delta = note.start_frame - self.current_frame
            if (delta < -CHART_SAMPLE_RATE and not is_active_hold) or delta > lookahead:
                continue
            y = target_y - delta / lookahead * target_y
            height = max(10, note.duration_frames / lookahead * target_y)
            if is_active_hold:
                y = target_y
                height = max(10, (note.end_frame - self.current_frame) / lookahead * target_y)
            color = QColor("#42DDF8") if note.confidence >= 0.5 else QColor("#FFBD4A")
            if state:
                color = QColor(JUDGEMENT_STYLE[state[0]][2])
                color.setAlpha(220 if is_active_hold else max(20, round(255 * (1 - (now - state[1]) / 0.42))))
            rect_x = round(key_index * lane_width + 4)
            rect_w = max(5, round(lane_width - 8))
            painter.setPen(QPen(QColor(220, 252, 255, color.alpha()), 1.5))
            painter.setBrush(color)
            painter.drawRoundedRect(rect_x, round(y - height), rect_w, round(height), 4, 4)

        painter.setPen(QPen(QColor("#D9FCFF"), 3))
        painter.drawLine(0, target_y, self.width(), target_y)
        painter.setPen(QPen(QColor(61, 235, 255, 70), 9))
        painter.drawLine(0, target_y, self.width(), target_y)

        bindings = bindings_for(key_count)
        for key_index, binding in enumerate(bindings):
            x = round(key_index * lane_width + 3)
            width = max(3, round(lane_width - 6))
            pressed = key_index in self.pressed_keys
            painter.setPen(QPen(QColor("#6EF2FF") if pressed else QColor("#34496E"), 1.5))
            painter.setBrush(QColor("#1A5A70") if pressed else QColor("#121A30"))
            painter.drawRoundedRect(x, target_y + 8, width, receptor_height - 12, 7, 7)
            painter.setPen(QColor("#FFFFFF"))
            key_size = max(10, min(18, round(lane_width * 0.25)))
            painter.setFont(QFont("Segoe UI", key_size, QFont.Weight.Bold))
            painter.drawText(x, target_y + 10, width, 30, Qt.AlignmentFlag.AlignCenter, binding.label)
            painter.setPen(QColor("#8FA3C8"))
            painter.setFont(QFont("Segoe UI", max(6, min(9, round(lane_width * 0.13)))))
            painter.drawText(x, target_y + 39, width, 22, Qt.AlignmentFlag.AlignCenter, self.pitch_labels[key_index])

        for effect in self.effects:
            age = now - effect.started_at
            if effect.key_index is None:
                continue
            _text, _foreground, accent = JUDGEMENT_STYLE[effect.result.judgement]
            alpha = max(0, round(180 * (1 - age / 0.72)))
            for spark in range(5):
                angle = spark * 1.257 + effect.key_index * 0.31
                radius = 16 + age * 85
                cx = (effect.key_index + 0.5) * lane_width + math.cos(angle) * radius
                cy = target_y - 12 + math.sin(angle) * radius * 0.45
                particle = QColor(accent)
                particle.setAlpha(alpha)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(particle)
                painter.drawEllipse(round(cx - 2), round(cy - 2), 5, 5)

        if self.effects:
            effect = self.effects[-1]
            age = now - effect.started_at
            text, foreground, accent = JUDGEMENT_STYLE[effect.result.judgement]
            opacity = max(0.0, min(1.0, 1 - max(0.0, age - 0.42) / 0.30))
            painter.setOpacity(opacity)
            scale = 1.0 + (0.13 * max(0.0, 1 - age / 0.16))
            painter.setPen(QPen(accent, 7))
            painter.setFont(QFont("Segoe UI", round(25 * scale), QFont.Weight.Black))
            feedback_y = max(90, target_y - 150)
            painter.drawText(0, feedback_y, self.width(), 45, Qt.AlignmentFlag.AlignCenter, text)
            painter.setPen(foreground)
            painter.drawText(0, feedback_y, self.width(), 45, Qt.AlignmentFlag.AlignCenter, text)
            if effect.result.delta_frames is not None and effect.result.judgement not in (Judgement.MISS, Judgement.GHOST):
                delta_ms = effect.result.delta_frames / 48
                painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
                painter.setPen(QColor("#B8C4DD"))
                painter.drawText(0, feedback_y + 43, self.width(), 24, Qt.AlignmentFlag.AlignCenter, f"{delta_ms:+.1f} ms")
            if effect.combo >= 10:
                painter.setFont(QFont("Segoe UI", round(18 * scale), QFont.Weight.Bold))
                painter.setPen(QColor("#F4F7FF"))
                painter.drawText(0, feedback_y - 35, self.width(), 28, Qt.AlignmentFlag.AlignCenter, f"{effect.combo} COMBO")
            painter.setOpacity(1.0)

        if self.effects or self.note_states:
            self.update()


class GameWindow(QWidget):
    def __init__(self, song, repository, parent=None):
        super().__init__(parent)
        if not song.chart_path:
            raise ValueError("song has no chart")
        self.song = song
        self.repository = repository
        self.chart = load_chart(song.chart_path)
        if hasattr(song, "status"):
            self.repository.update_status(
                song.id, song.status, chart_path=song.chart_path, chart_revision=self.chart.chart_revision
            )
        self.settings = Settings.load(AppPaths.discover().settings)
        self.audio: AudioEngine | None = None
        self.session: GameplaySession | None = None
        self.sequence = 0
        self.active_pitches: dict[int, int] = {}
        self.completed = False
        cover = QPixmap(str(song.cover_path)) if song.cover_path and song.cover_path.is_file() else QPixmap()
        self.cover = _blur_pixmap(cover)
        self.setWindowTitle(f"KeyRhythm — {song.title}")
        self.setMinimumSize(900, 650)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(10)
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        self.song_label = QLabel(song.title)
        self.song_label.setObjectName("title")
        artist = QLabel(song.artist or "未知艺术家")
        artist.setObjectName("muted")
        title_box.addWidget(self.song_label)
        title_box.addWidget(artist)
        header.addLayout(title_box, 1)

        self.chart_selector = QComboBox()
        self.chart_selector.setToolTip("切换难度将从头重新开始当前歌曲")
        display_names = {"piano": "17 键旋律", "lane_4_easy": "4K EASY", "lane_6_normal": "6K NORMAL", "lane_8_hard": "8K HARD"}
        for name in self.chart.charts:
            self.chart_selector.addItem(display_names.get(name, name), name)
        self.chart_selector.currentIndexChanged.connect(self._select_chart)
        header.addWidget(self.chart_selector)
        retry_button = QPushButton("重试")
        retry_button.clicked.connect(self.retry)
        header.addWidget(retry_button)
        self.pause_button = QPushButton("暂停")
        self.pause_button.clicked.connect(self.toggle_pause)
        header.addWidget(self.pause_button)
        root.addLayout(header)

        hud = QHBoxLayout()
        self.combo_label = QLabel("0 COMBO")
        self.combo_label.setObjectName("muted")
        hud.addWidget(self.combo_label)
        hud.addStretch(1)
        self.score_label = QLabel("SCORE 0000000")
        self.score_label.setStyleSheet("font-size: 19px; font-weight: 700; color: #F4F7FF;")
        self.accuracy_label = QLabel("ACC 0.00%")
        self.accuracy_label.setStyleSheet("font-size: 17px; color: #3DEBFF;")
        hud.addWidget(self.score_label)
        hud.addSpacing(18)
        hud.addWidget(self.accuracy_label)
        root.addLayout(hud)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        root.addWidget(self.progress)
        self.canvas = NoteCanvas(self.chart)
        root.addWidget(self.canvas, 1)

        self.overlay = self._create_overlay()
        self.overlay.hide()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self._start()

    def _create_overlay(self) -> QFrame:
        overlay = QFrame(self)
        overlay.setStyleSheet("QFrame { background: rgba(7, 9, 20, 235); border: 1px solid #3A4A73; border-radius: 18px; }")
        layout = QVBoxLayout(overlay)
        layout.setContentsMargins(42, 32, 42, 32)
        self.overlay_title = QLabel("PAUSED")
        self.overlay_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay_title.setStyleSheet("font-size: 32px; font-weight: 800; color: #3DEBFF; border: 0;")
        self.overlay_body = QLabel()
        self.overlay_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay_body.setStyleSheet("font-size: 16px; color: #E4E9F6; border: 0;")
        layout.addWidget(self.overlay_title)
        layout.addWidget(self.overlay_body)
        self.volume_box = QFrame()
        self.volume_box.setStyleSheet("border: 0; background: transparent;")
        volume_layout = QVBoxLayout(self.volume_box)
        for label, bus, value in (
            ("原曲音量", AudioBus.BACKING, self.settings.backing_volume),
            ("琴声音量", AudioBus.INSTRUMENT, self.settings.instrument_volume),
            ("总音量", AudioBus.MASTER, self.settings.master_volume),
        ):
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(value)
            slider.valueChanged.connect(lambda current, selected=bus: self.audio and self.audio.set_bus_volume(selected, current))
            row.addWidget(slider, 1)
            volume_layout.addLayout(row)
        layout.addWidget(self.volume_box)
        buttons = QHBoxLayout()
        self.overlay_primary = QPushButton("继续")
        self.overlay_primary.setObjectName("primary")
        self.overlay_primary.clicked.connect(self._overlay_primary_action)
        retry = QPushButton("重新开始")
        retry.clicked.connect(self.retry)
        close = QPushButton("返回曲库")
        close.clicked.connect(self.close)
        buttons.addWidget(retry)
        buttons.addWidget(self.overlay_primary)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        overlay.setFixedWidth(480)
        return overlay

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        seed = int(hashlib.sha256(self.song.id.encode()).hexdigest()[:6], 16)
        gradient.setColorAt(0, QColor(7 + seed % 12, 8, 27 + seed % 18))
        gradient.setColorAt(0.55, QColor("#080B18"))
        gradient.setColorAt(1, QColor(24 + seed % 18, 7, 38 + seed % 22))
        painter.fillRect(self.rect(), gradient)
        if not self.cover.isNull():
            painter.setOpacity(0.12)
            painter.drawPixmap(self.rect(), self.cover.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        painter.setOpacity(1.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(61, 235, 255, 28))
        seed = int(hashlib.sha256((self.song.id + "particles").encode()).hexdigest()[:8], 16)
        for index in range(24):
            x = (seed * (index + 17) * 37) % max(1, self.width())
            y = (seed * (index + 31) * 19) % max(1, self.height())
            radius = 1 + (seed + index) % 3
            painter.drawEllipse(round(x), round(y), radius, radius)
        super().paintEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "overlay"):
            self._position_overlay()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.setFocus)

    def _position_overlay(self) -> None:
        width = min(480, self.width() - 60)
        self.overlay.setFixedWidth(width)
        self.overlay.adjustSize()
        self.overlay.move((self.width() - self.overlay.width()) // 2, (self.height() - self.overlay.height()) // 2)

    def _start(self) -> None:
        try:
            self.audio = AudioEngine(output_device=self.settings.output_device or None)
            self.audio.load_song(self.song.normalized_path)
            self.audio.set_bus_volume(AudioBus.BACKING, self.settings.backing_volume)
            self.audio.set_bus_volume(AudioBus.INSTRUMENT, self.settings.instrument_volume)
            self.audio.set_bus_volume(AudioBus.MASTER, self.settings.master_volume)
            self._select_chart()
            self.audio.play()
            self.timer.start()
        except (AudioUnavailableError, Exception) as error:
            QMessageBox.critical(self, "无法启动音频", str(error))

    def _select_chart(self) -> None:
        name = self.chart_selector.currentData()
        if not name:
            return
        restart = self.audio is not None and self.session is not None
        if restart:
            self.audio.seek(0)
        playable = self.chart.charts[name]
        self.canvas.set_playable(playable)
        generation = self.audio.session_generation if self.audio else 0
        self.session = GameplaySession(JudgementEngine(self.chart.notes, playable), generation)
        self.active_pitches.clear()
        self.completed = False
        if restart:
            if self.audio.state.value != "playing":
                self.audio.play()
            self.timer.start()
            self.progress.setValue(0)
            self.score_label.setText("SCORE 0000000")
            self.accuracy_label.setText("ACC 0.00%")
            self.combo_label.setText("0 COMBO")
            self.overlay.hide()
            self.pause_button.setText("暂停")
            self.setFocus()

    def _tick(self) -> None:
        if not self.audio:
            return
        snapshot = self.audio.get_timeline_snapshot()
        self.canvas.current_frame = snapshot.chart_frame + self.settings.visual_offset_frames
        self.canvas.update()
        self.progress.setValue(min(1000, round(snapshot.chart_frame / max(1, self.chart.duration_frames) * 1000)))
        if self.session:
            for result in self.session.advance(snapshot.chart_frame):
                self.canvas.apply_judgement(result, self.session.combo)
            self.score_label.setText(f"SCORE {self.session.score:07d}")
            self.accuracy_label.setText(f"ACC {self.session.accuracy:.2%}")
            self.combo_label.setText(f"{self.session.combo} COMBO")
        if snapshot.chart_frame >= self.chart.duration_frames:
            self.audio.pause()
            self.timer.stop()
            self.finish_session()

    def toggle_pause(self) -> None:
        if not self.audio or self.completed:
            return
        if self.audio.state.value == "playing":
            self.audio.pause()
            self.timer.stop()
            self.active_pitches.clear()
            self.canvas.clear_feedback()
            self._show_pause_overlay()
        else:
            self.overlay.hide()
            self.audio.resume()
            self.timer.start()
            self.pause_button.setText("暂停")
            self.setFocus()

    def _show_pause_overlay(self) -> None:
        self.pause_button.setText("继续")
        self.overlay_title.setText("PAUSED")
        self.overlay_body.setText("调整音量，或在准备好后继续演奏")
        self.volume_box.show()
        self.overlay_primary.setText("继续")
        self.overlay.show()
        self._position_overlay()
        self.overlay.raise_()

    def _overlay_primary_action(self) -> None:
        if self.completed:
            self.retry()
        else:
            self.toggle_pause()

    def retry(self) -> None:
        if not self.audio or not self.session:
            return
        self.audio.seek(0)
        self.session.reset(self.audio.session_generation)
        self.completed = False
        self.active_pitches.clear()
        self.canvas.clear_feedback()
        self.overlay.hide()
        self.audio.play()
        self.timer.start()
        self.pause_button.setText("暂停")
        self.setFocus()

    @staticmethod
    def _grade(accuracy: float) -> str:
        if accuracy >= 1.0:
            return "SS"
        if accuracy >= 0.95:
            return "S"
        if accuracy >= 0.90:
            return "A"
        if accuracy >= 0.80:
            return "B"
        if accuracy >= 0.70:
            return "C"
        return "D"

    def finish_session(self) -> None:
        if self.completed or not self.session or not self.canvas.playable:
            return
        self.completed = True
        counts = self.session.counts
        playable = self.canvas.playable
        score = Score(
            song_id=self.song.id,
            chart_revision=self.chart.chart_revision,
            chart_hash=hashlib.sha256(Path(self.song.chart_path).read_bytes()).hexdigest(),
            mode=playable.mode,
            difficulty=playable.difficulty,
            total_score=self.session.score,
            accuracy=self.session.accuracy,
            max_combo=self.session.max_combo,
            perfect_count=counts[Judgement.PERFECT],
            good_count=counts[Judgement.GOOD],
            bad_count=counts[Judgement.BAD],
            wrong_count=counts[Judgement.WRONG],
            miss_count=counts[Judgement.MISS],
            hold_break_count=counts[Judgement.HOLD_BREAK],
        )
        self.repository.save_score(score)
        self.overlay_title.setText(f"{self._grade(self.session.accuracy)}  RESULT")
        self.overlay_body.setText(
            f"SCORE  {self.session.score:07d}\n"
            f"ACCURACY  {self.session.accuracy:.2%}    MAX COMBO  {self.session.max_combo}\n\n"
            f"PERFECT {counts[Judgement.PERFECT]}    GOOD {counts[Judgement.GOOD]}    BAD {counts[Judgement.BAD]}\n"
            f"WRONG {counts[Judgement.WRONG]}    MISS {counts[Judgement.MISS]}    HOLD BREAK {counts[Judgement.HOLD_BREAK]}"
        )
        self.volume_box.hide()
        self.overlay_primary.setText("再来一次")
        self.overlay.show()
        self._position_overlay()
        self.overlay.raise_()

    def _mapping(self, key: int) -> int | None:
        playable = self.canvas.playable
        return key_index_for(playable.key_count, key) if playable else None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat() or not self.audio or not self.session or self.completed:
            return
        key_index = self._mapping(event.key())
        if key_index is None:
            if event.key() == Qt.Key.Key_Escape:
                self.toggle_pause()
                return
            return super().keyPressEvent(event)
        playable = self.canvas.playable
        assert playable is not None
        self.canvas.set_key_pressed(key_index, True)
        self.sequence += 1
        input_event = InputEvent(
            session_generation=self.audio.session_generation,
            sequence=self.sequence,
            physical_key=str(event.key()),
            action=InputAction.PRESS,
            host_time_ns=time.monotonic_ns(),
            midi_pitch=playable.key_pitch_map[key_index],
            key_index=key_index,
        )
        mapped = self.audio.map_input_time(input_event.host_time_ns) + self.settings.judgement_offset_frames
        result = self.session.handle(input_event, mapped)
        sounding = result.sounding_pitch if result else input_event.midi_pitch
        if result:
            self.canvas.apply_judgement(result, self.session.combo)
        if sounding is not None:
            self.active_pitches[event.key()] = sounding
        self.audio.submit_input(dataclasses.replace(input_event, midi_pitch=sounding))

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat() or not self.audio or not self.session:
            return
        key_index = self._mapping(event.key())
        if key_index is None:
            return super().keyReleaseEvent(event)
        self.canvas.set_key_pressed(key_index, False)
        self.sequence += 1
        sounding = self.active_pitches.pop(event.key(), None)
        input_event = InputEvent(
            session_generation=self.audio.session_generation,
            sequence=self.sequence,
            physical_key=str(event.key()),
            action=InputAction.RELEASE,
            host_time_ns=time.monotonic_ns(),
            midi_pitch=sounding,
            key_index=key_index,
        )
        mapped = self.audio.map_input_time(input_event.host_time_ns) + self.settings.judgement_offset_frames
        result = self.session.handle(input_event, mapped)
        if result:
            self.canvas.apply_judgement(result, self.session.combo)
        self.audio.submit_input(input_event)

    def changeEvent(self, event) -> None:
        if (
            event.type() == QEvent.Type.WindowDeactivate
            and self.audio
            and self.audio.state.value == "playing"
            and not self.completed
        ):
            self.audio.pause()
            self.timer.stop()
            self.active_pitches.clear()
            self.canvas.clear_feedback()
            self._show_pause_overlay()
        super().changeEvent(event)

    def closeEvent(self, event) -> None:
        self.timer.stop()
        if self.audio:
            self.audio.close()
        super().closeEvent(event)
