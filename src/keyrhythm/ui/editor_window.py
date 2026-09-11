from __future__ import annotations

import array
import copy
import wave

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from keyrhythm.config import CHART_SAMPLE_RATE
from keyrhythm.domain.chart import ChartNote, PlayableChart, load_chart, next_note_id, save_chart_atomic
from keyrhythm.domain.difficulty import generate_playable_charts
from keyrhythm.domain.models import SongStatus
from keyrhythm.ui.key_layout import bindings_for, midi_note_name


class ChartOverview(QWidget):
    def __init__(self, song, chart, parent=None):
        super().__init__(parent)
        self.chart = chart
        self.peaks: list[float] = []
        self.setMinimumHeight(145)
        try:
            with wave.open(str(song.normalized_path), "rb") as handle:
                block = max(1, handle.getnframes() // 700)
                while raw := handle.readframes(block):
                    values = array.array("h")
                    values.frombytes(raw)
                    self.peaks.append(max((abs(value) for value in values), default=0) / 32768)
        except Exception:
            self.peaks = []

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#0B1122"))
        gradient.setColorAt(1, QColor("#151C35"))
        painter.fillRect(self.rect(), gradient)
        center = self.height() // 2
        painter.setPen(QPen(QColor("#3A8DB1"), 1))
        if self.peaks:
            for x in range(self.width()):
                value = self.peaks[min(len(self.peaks) - 1, x * len(self.peaks) // max(1, self.width()))]
                height = round(value * (center - 12))
                painter.drawLine(x, center - height, x, center + height)
        painter.setPen(QPen(QColor(61, 235, 255, 65), 1))
        for beat in self.chart.beat_frames:
            x = round(beat / self.chart.duration_frames * self.width())
            painter.drawLine(x, 0, x, self.height())
        painter.setPen(QPen(QColor("#F04BFF"), 2))
        for note in self.chart.notes:
            x = round(note.start_frame / self.chart.duration_frames * self.width())
            painter.drawLine(x, 4, x, 18)


class MappingPreview(QWidget):
    def __init__(self, chart, parent=None):
        super().__init__(parent)
        self.chart = chart
        self.playable: PlayableChart | None = None
        self.setMinimumHeight(130)

    def set_playable(self, playable: PlayableChart) -> None:
        self.playable = playable
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0B1020"))
        if not self.playable:
            return
        note_map = self.chart.note_map()
        key_count = self.playable.key_count
        width = self.width() / key_count
        counts = [0] * key_count
        ranges: list[list[int]] = [[] for _ in range(key_count)]
        for event in self.playable.key_events:
            counts[event.key_index] += 1
            ranges[event.key_index].append(note_map[event.note_id].midi_pitch)
        maximum = max(counts, default=1) or 1
        for index, binding in enumerate(bindings_for(key_count)):
            x = round(index * width + 3)
            w = max(3, round(width - 6))
            painter.setPen(QPen(QColor("#30446E"), 1))
            painter.setBrush(QColor("#131B31"))
            painter.drawRoundedRect(x, 8, w, self.height() - 16, 6, 6)
            bar_height = round((self.height() - 55) * counts[index] / maximum)
            painter.fillRect(x + 3, self.height() - 30 - bar_height, max(1, w - 6), bar_height, QColor(61, 235, 255, 110))
            painter.setPen(QColor("#FFFFFF"))
            painter.setFont(QFont("Segoe UI", max(7, min(12, round(width * 0.16))), QFont.Weight.Bold))
            painter.drawText(x, self.height() - 28, w, 18, Qt.AlignmentFlag.AlignCenter, binding.label)
            pitches = sorted(set(ranges[index]))
            label = midi_note_name(self.playable.key_pitch_map[index])
            if len(pitches) > 1:
                label = f"{midi_note_name(pitches[0])}–{midi_note_name(pitches[-1])}"
            elif pitches:
                label = midi_note_name(pitches[0])
            painter.setPen(QColor("#8FA3C8"))
            painter.setFont(QFont("Segoe UI", max(5, min(8, round(width * 0.1)))))
            painter.drawText(x, self.height() - 13, w, 12, Qt.AlignmentFlag.AlignCenter, label)


class EditorWindow(QWidget):
    def __init__(self, song, repository, parent=None):
        super().__init__(parent)
        self.song = song
        self.repository = repository
        self.chart = load_chart(song.chart_path)
        if hasattr(song, "status"):
            self.repository.update_status(
                song.id, song.status, chart_path=song.chart_path, chart_revision=self.chart.chart_revision
            )
        self.history: list[list[ChartNote]] = []
        self.future: list[list[ChartNote]] = []
        self.setWindowTitle(f"校谱 — {song.title}")
        self.setMinimumSize(900, 650)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        title_row = QHBoxLayout()
        title_box = QVBoxLayout()
        eyebrow = QLabel("CHART WORKSHOP")
        eyebrow.setObjectName("eyebrow")
        title = QLabel(song.title)
        title.setObjectName("title")
        title_box.addWidget(eyebrow)
        title_box.addWidget(title)
        title_row.addLayout(title_box, 1)
        self.save_button = QPushButton("保存新修订")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save)
        title_row.addWidget(self.save_button)
        root.addLayout(title_row)
        root.addWidget(ChartOverview(song, self.chart))

        mapping_card = QFrame()
        mapping_card.setObjectName("panel")
        mapping_layout = QVBoxLayout(mapping_card)
        mapping_header = QHBoxLayout()
        mapping_header.addWidget(QLabel("动态键位映射"))
        self.mapping_selector = QComboBox()
        names = {"piano": "17 键旋律", "lane_4_easy": "4K EASY", "lane_6_normal": "6K NORMAL", "lane_8_hard": "8K HARD"}
        for name in self.chart.charts:
            self.mapping_selector.addItem(names.get(name, name), name)
        self.mapping_selector.currentIndexChanged.connect(self.refresh_mapping)
        mapping_header.addWidget(self.mapping_selector)
        regenerate = QPushButton("重新生成当前映射")
        regenerate.clicked.connect(self.regenerate)
        mapping_header.addWidget(regenerate)
        mapping_header.addStretch(1)
        self.mapping_stats = QLabel()
        self.mapping_stats.setObjectName("muted")
        mapping_header.addWidget(self.mapping_stats)
        mapping_layout.addLayout(mapping_header)
        self.mapping_preview = MappingPreview(self.chart)
        mapping_layout.addWidget(self.mapping_preview)
        root.addWidget(mapping_card)

        controls = QHBoxLayout()
        self.offset = QSpinBox()
        self.offset.setRange(-10_000, 10_000)
        self.offset.setSuffix(" ms")
        controls.addWidget(QLabel("整体偏移"))
        controls.addWidget(self.offset)
        offset_button = QPushButton("应用")
        offset_button.clicked.connect(self.apply_offset)
        controls.addWidget(offset_button)
        for text, callback in (("＋ 添加", self.add_note), ("删除", self.delete_note), ("撤销", self.undo), ("重做", self.redo)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addStretch(1)
        root.addLayout(controls)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "开始 (ms)", "时长 (ms)", "MIDI", "置信度"])
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self.table, 1)
        self.populate()
        self.refresh_mapping()

    def snapshot(self) -> None:
        self._read_table()
        self.history.append(copy.deepcopy(self.chart.notes))
        self.future.clear()

    def populate(self) -> None:
        self.table.setRowCount(len(self.chart.notes))
        for row, note in enumerate(self.chart.notes):
            values = [
                note.id,
                f"{note.start_frame * 1000 / CHART_SAMPLE_RATE:.1f}",
                f"{note.duration_frames * 1000 / CHART_SAMPLE_RATE:.1f}",
                str(note.midi_pitch),
                f"{note.confidence:.3f}",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if column == 4 and note.confidence < 0.5:
                    item.setForeground(QColor("#FFB84D"))
                self.table.setItem(row, column, item)

    def _read_table(self) -> None:
        notes: list[ChartNote] = []
        for row in range(self.table.rowCount()):
            old = next((note for note in self.chart.notes if note.id == self.table.item(row, 0).text()), None)
            notes.append(ChartNote(
                id=self.table.item(row, 0).text(),
                start_frame=max(0, round(float(self.table.item(row, 1).text()) * CHART_SAMPLE_RATE / 1000)),
                duration_frames=max(1, round(float(self.table.item(row, 2).text()) * CHART_SAMPLE_RATE / 1000)),
                midi_pitch=max(0, min(127, int(self.table.item(row, 3).text()))),
                confidence=max(0.0, min(1.0, float(self.table.item(row, 4).text()))),
                velocity=old.velocity if old else 90,
                source=old.source if old else "manual",
                manually_edited=True,
            ))
        self.chart.notes = sorted(notes, key=lambda note: (note.start_frame, note.midi_pitch))

    def add_note(self) -> None:
        self.snapshot()
        self.chart.notes.append(ChartNote(next_note_id(self.chart.notes), 0, CHART_SAMPLE_RATE // 4, 60, manually_edited=True))
        self.populate()

    def delete_note(self) -> None:
        rows = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        self.snapshot()
        for row in rows:
            del self.chart.notes[row]
        self.populate()

    def apply_offset(self) -> None:
        self.snapshot()
        frames = round(self.offset.value() * CHART_SAMPLE_RATE / 1000)
        for note in self.chart.notes:
            note.start_frame = max(0, min(self.chart.duration_frames - note.duration_frames, note.start_frame + frames))
            note.manually_edited = True
        self.populate()

    def regenerate(self) -> None:
        self._read_table()
        name = self.mapping_selector.currentData()
        generated = generate_playable_charts(self.chart.notes)
        if name:
            self.chart.charts[name] = generated[name]
        self.refresh_mapping()

    def refresh_mapping(self) -> None:
        name = self.mapping_selector.currentData()
        if not name:
            return
        playable = self.chart.charts[name]
        self.mapping_preview.set_playable(playable)
        self.mapping_stats.setText(
            f"{playable.key_count} 键  ·  {len(playable.key_events)} 音符  ·  冲突舍弃 {playable.collision_drop_count}"
        )

    def undo(self) -> None:
        if not self.history:
            return
        self.future.append(copy.deepcopy(self.chart.notes))
        self.chart.notes = self.history.pop()
        self.chart.charts = generate_playable_charts(self.chart.notes)
        self.populate()
        self.refresh_mapping()

    def redo(self) -> None:
        if not self.future:
            return
        self.history.append(copy.deepcopy(self.chart.notes))
        self.chart.notes = self.future.pop()
        self.chart.charts = generate_playable_charts(self.chart.notes)
        self.populate()
        self.refresh_mapping()

    def save(self) -> None:
        try:
            self._read_table()
            self.chart.charts = generate_playable_charts(self.chart.notes)
            self.chart.chart_revision += 1
            self.chart.edit_patches.append({"revision": self.chart.chart_revision, "operation": "manual_editor_save"})
            save_chart_atomic(self.chart, self.song.chart_path)
            self.repository.update_status(
                self.song.id,
                SongStatus.READY,
                chart_path=self.song.chart_path,
                chart_revision=self.chart.chart_revision,
            )
            self.refresh_mapping()
            QMessageBox.information(self, "已保存", f"谱面修订 {self.chart.chart_revision} 已保存")
        except Exception as error:
            QMessageBox.critical(self, "保存失败", str(error))
