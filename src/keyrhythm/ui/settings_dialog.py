from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from keyrhythm.audio.devices import list_output_devices
from keyrhythm.cli import doctor
from keyrhythm.settings import Settings


class SettingsDialog(QDialog):
    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self.settings = Settings.load(path)
        self.setWindowTitle("KeyRhythm 设置与诊断")
        self.setMinimumWidth(620)
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 22)
        title = QLabel("设置与设备诊断")
        title.setObjectName("title")
        subtitle = QLabel("校准音频输出，并为演奏画面修正时间偏移")
        subtitle.setObjectName("muted")
        root.addWidget(title)
        root.addWidget(subtitle)

        audio_card, audio_form = self._card("AUDIO OUTPUT")
        self.device = QComboBox()
        self.device.addItem("系统默认", "")
        try:
            import sounddevice as sd
            for item in list_output_devices(sd):
                self.device.addItem(f"{item.label}（低延迟 {item.low_latency_seconds * 1000:.1f} ms）", item.key)
        except Exception:
            pass
        self.device.setCurrentIndex(max(0, self.device.findData(self.settings.output_device)))
        audio_form.addRow("输出设备", self.device)
        self.backing = self._spin(self.settings.backing_volume, 0, 100, "%")
        self.instrument = self._spin(self.settings.instrument_volume, 0, 100, "%")
        self.master = self._spin(self.settings.master_volume, 0, 100, "%")
        audio_form.addRow("原曲音量", self.backing)
        audio_form.addRow("琴声音量", self.instrument)
        audio_form.addRow("总音量", self.master)
        root.addWidget(audio_card)

        timing_card, timing_form = self._card("TIMING CALIBRATION")
        self.judgement = self._spin(round(self.settings.judgement_offset_frames / 48), -500, 500, " ms")
        self.visual = self._spin(round(self.settings.visual_offset_frames / 48), -500, 500, " ms")
        timing_form.addRow("判定偏移", self.judgement)
        timing_form.addRow("画面偏移", self.visual)
        root.addWidget(timing_card)

        diagnostics_card, diagnostics_form = self._card("SYSTEM DIAGNOSTICS")
        report = doctor()
        diagnostics = QLabel(
            f"Python {report['python']}  ·  3.11 支持：{report['supported_python']}\n"
            f"FFmpeg：{bool(report['executables']['ffmpeg'])}  ·  FluidSynth：{bool(report['executables']['fluidsynth'])}  ·  SoundFont：{bool(report['assets']['soundfont'])}\n"
            f"自动制谱 Worker：{bool(report['executables']['analysis_worker'])}  ·  冻结版：{report['frozen']}\n"
            f"音频模块：{report['modules']['sounddevice']}  ·  分析模块：{report['modules']['basic_pitch']}"
        )
        diagnostics.setWordWrap(True)
        diagnostics.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        diagnostics_form.addRow(diagnostics)
        root.addWidget(diagnostics_card)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存设置")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def _card(label: str) -> tuple[QFrame, QFormLayout]:
        card = QFrame()
        card.setObjectName("panel")
        layout = QVBoxLayout(card)
        heading = QLabel(label)
        heading.setObjectName("eyebrow")
        form = QFormLayout()
        form.setSpacing(12)
        layout.addWidget(heading)
        layout.addLayout(form)
        return card, form

    @staticmethod
    def _spin(value: int, minimum: int, maximum: int, suffix: str = "") -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        return spin

    def accept(self) -> None:
        self.settings.output_device = self.device.currentData()
        self.settings.backing_volume = self.backing.value()
        self.settings.instrument_volume = self.instrument.value()
        self.settings.master_volume = self.master.value()
        self.settings.judgement_offset_frames = self.judgement.value() * 48
        self.settings.visual_offset_frames = self.visual.value() * 48
        self.settings.save(self.path)
        super().accept()
