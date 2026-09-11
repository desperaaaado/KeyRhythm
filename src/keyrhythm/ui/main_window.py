from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from keyrhythm.config import AppPaths
from keyrhythm.library import Database, SongRepository
from keyrhythm.library.importer import SongImporter
from keyrhythm.library.presets import ensure_builtin_song
from keyrhythm.ui.editor_window import EditorWindow
from keyrhythm.ui.game_window import GameWindow
from keyrhythm.ui.settings_dialog import SettingsDialog


class ImportWorker(QObject):
    progress = Signal(str, float)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, importer: SongImporter, path: Path):
        super().__init__()
        self.importer = importer
        self.path = path

    def run(self) -> None:
        try:
            self.succeeded.emit(self.importer.import_file(self.path, progress=self.progress.emit))
        except Exception as error:
            self.failed.emit(str(error))
        finally:
            self.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KeyRhythm")
        self.setMinimumSize(900, 650)
        self.paths = AppPaths.discover()
        self.paths.ensure()
        self.database = Database(self.paths.database)
        self.database.migrate()
        self.repository = SongRepository(self.database)
        ensure_builtin_song(self.paths, self.repository)
        self.importer = SongImporter(self.paths, self.repository)
        self.child_windows: list[QWidget] = []
        self.import_thread: QThread | None = None
        self.import_worker: ImportWorker | None = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(18)

        hero = QHBoxLayout()
        brand = QVBoxLayout()
        eyebrow = QLabel("LOCAL RHYTHM STAGE")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("KEYRHYTHM")
        title.setObjectName("title")
        subtitle = QLabel("选择一首本地歌曲，让键盘成为你的乐器")
        subtitle.setObjectName("muted")
        brand.addWidget(eyebrow)
        brand.addWidget(title)
        brand.addWidget(subtitle)
        hero.addLayout(brand, 1)
        settings_button = QPushButton("设置与诊断")
        settings_button.clicked.connect(self.open_settings)
        hero.addWidget(settings_button)
        import_button = QPushButton("＋ 导入音乐")
        import_button.setObjectName("primary")
        import_button.clicked.connect(self.import_song)
        hero.addWidget(import_button)
        root.addLayout(hero)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索本地标题、艺术家或标签…")
        self.search.textChanged.connect(self.refresh)
        root.addWidget(self.search)

        content = QHBoxLayout()
        content.setSpacing(18)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["标题", "艺术家", "时长", "状态", "标签"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 5):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(self.play_selected)
        self.table.itemSelectionChanged.connect(self.update_detail)
        content.addWidget(self.table, 3)

        detail = QFrame()
        detail.setObjectName("panel")
        detail.setMinimumWidth(270)
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(22, 22, 22, 22)
        self.cover_label = QLabel("KR")
        self.cover_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cover_label.setFixedHeight(190)
        self.cover_label.setStyleSheet("background: #151F3A; border: 1px solid #34466F; border-radius: 12px; color: #3DEBFF; font-size: 46px; font-weight: 800;")
        self.detail_title = QLabel("选择歌曲")
        self.detail_title.setObjectName("title")
        self.detail_title.setWordWrap(True)
        self.detail_artist = QLabel("从左侧曲库选择一首歌曲")
        self.detail_artist.setObjectName("muted")
        self.detail_meta = QLabel()
        self.detail_meta.setWordWrap(True)
        detail_layout.addWidget(self.cover_label)
        detail_layout.addWidget(self.detail_title)
        detail_layout.addWidget(self.detail_artist)
        detail_layout.addWidget(self.detail_meta)
        detail_layout.addStretch(1)
        edit_button = QPushButton("校对谱面")
        edit_button.clicked.connect(self.edit_selected)
        self.play_button = QPushButton("开始演奏")
        self.play_button.setObjectName("primary")
        self.play_button.clicked.connect(self.play_selected)
        detail_layout.addWidget(edit_button)
        detail_layout.addWidget(self.play_button)
        content.addWidget(detail, 1)
        root.addLayout(content, 1)

        self.import_card = QFrame()
        self.import_card.setObjectName("panel")
        import_layout = QHBoxLayout(self.import_card)
        self.import_label = QLabel("正在导入")
        self.import_progress = QProgressBar()
        self.import_progress.setRange(0, 1000)
        self.import_progress.setTextVisible(False)
        import_layout.addWidget(self.import_label)
        import_layout.addWidget(self.import_progress, 1)
        self.import_card.hide()
        root.addWidget(self.import_card)
        self.statusBar().showMessage(str(self.paths.root))
        self.refresh()

    def refresh(self, *_args) -> None:
        selected_id = self.selected_song().id if self.selected_song() else None
        songs = self.repository.search(self.search.text())
        self.table.setRowCount(len(songs))
        selected_row = -1
        for row, song in enumerate(songs):
            values = [song.title, song.artist or "—", f"{song.duration_frames / 48000:.1f}s", song.status.value, ", ".join(song.tags)]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, song.id)
                self.table.setItem(row, column, item)
            if song.id == selected_id:
                selected_row = row
        if songs:
            self.table.selectRow(selected_row if selected_row >= 0 else 0)
        else:
            self.update_detail()

    def selected_song(self):
        row = self.table.currentRow()
        if row < 0 or not self.table.item(row, 0):
            return None
        return self.repository.get(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))

    def update_detail(self) -> None:
        song = self.selected_song()
        if not song:
            self.detail_title.setText("选择歌曲")
            self.detail_artist.setText("从左侧曲库选择一首歌曲")
            self.detail_meta.clear()
            self.cover_label.setPixmap(QPixmap())
            self.cover_label.setText("KR")
            return
        self.detail_title.setText(song.title)
        self.detail_artist.setText(song.artist or "未知艺术家")
        minutes, seconds = divmod(round(song.duration_frames / 48000), 60)
        self.detail_meta.setText(f"{minutes}:{seconds:02d}  ·  {song.status.value}\n{', '.join(song.tags) or '暂无标签'}")
        if song.cover_path and song.cover_path.is_file():
            pixmap = QPixmap(str(song.cover_path)).scaled(230, 190, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self.cover_label.setText("")
            self.cover_label.setPixmap(pixmap)
        else:
            self.cover_label.setPixmap(QPixmap())
            self.cover_label.setText("KR")

    def import_song(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(self, "导入本地音乐", "", "Audio (*.mp3 *.wav *.flac *.m4a)")
        if not path:
            return
        if self.import_thread:
            QMessageBox.warning(self, "正在导入", "请等待当前导入任务完成")
            return
        self.import_thread = QThread(self)
        self.import_worker = ImportWorker(self.importer, Path(path))
        worker = self.import_worker
        worker.moveToThread(self.import_thread)
        self.import_thread.started.connect(worker.run)
        worker.progress.connect(self._show_import_progress)
        worker.succeeded.connect(self._import_succeeded)
        worker.failed.connect(lambda message: QMessageBox.critical(self, "导入失败", message))
        worker.finished.connect(self.import_thread.quit)
        worker.finished.connect(worker.deleteLater)
        self.import_thread.finished.connect(self._clear_import_thread)
        self.import_card.show()
        self.import_thread.start()

    def _show_import_progress(self, stage: str, value: float) -> None:
        labels = {
            "validate": "检查文件", "normalize": "标准化音频", "beat_detection": "检测节拍",
            "transcription": "提取旋律", "melody_selection": "生成可演奏旋律", "commit": "写入曲库",
        }
        self.import_label.setText(labels.get(stage, stage))
        self.import_progress.setValue(round(value * 1000))

    def _import_succeeded(self, song) -> None:
        self.statusBar().showMessage(f"已导入：{song.title}", 6000)
        self.refresh()

    def _clear_import_thread(self) -> None:
        if self.import_thread:
            self.import_thread.deleteLater()
        self.import_thread = None
        self.import_worker = None
        self.import_card.hide()

    def play_selected(self, *_args) -> None:
        song = self.selected_song()
        if not song or not song.chart_path:
            QMessageBox.warning(self, "无法演奏", "请选择一首已有谱面的歌曲")
            return
        window = GameWindow(song, self.repository)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.destroyed.connect(lambda: self._remove_window(window))
        self.child_windows.append(window)
        window.resize(1280, 720)
        window.show()

    def edit_selected(self) -> None:
        song = self.selected_song()
        if not song or not song.chart_path:
            QMessageBox.warning(self, "无法编辑", "请选择一首已有谱面的歌曲")
            return
        window = EditorWindow(song, self.repository)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.destroyed.connect(lambda: self._remove_window(window))
        self.child_windows.append(window)
        window.resize(1100, 720)
        window.show()

    def _remove_window(self, window: QWidget) -> None:
        if window in self.child_windows:
            self.child_windows.remove(window)

    def open_settings(self) -> None:
        SettingsDialog(self.paths.settings, self).exec()
