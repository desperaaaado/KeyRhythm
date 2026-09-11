from __future__ import annotations

import struct
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPen


PROJECT = Path(__file__).resolve().parents[1]


def main() -> int:
    application = QGuiApplication.instance() or QGuiApplication([])
    temporary_png = PROJECT / ".keyrhythm-dev" / "keyrhythm-icon.png"
    temporary_png.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(256, 256, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    gradient = QLinearGradient(22, 18, 236, 240)
    gradient.setColorAt(0.0, QColor("#09152F"))
    gradient.setColorAt(0.55, QColor("#15265A"))
    gradient.setColorAt(1.0, QColor("#45134F"))
    painter.setBrush(gradient)
    painter.setPen(QPen(QColor("#3DEBFF"), 7))
    painter.drawRoundedRect(QRect(12, 12, 232, 232), 48, 48)
    painter.setPen(QPen(QColor("#FF4FCB"), 6))
    painter.drawLine(42, 181, 78, 138)
    painter.drawLine(78, 138, 111, 166)
    painter.drawLine(111, 166, 151, 89)
    painter.drawLine(151, 89, 210, 127)
    painter.setPen(QColor("#F5FCFF"))
    painter.setFont(QFont("Segoe UI", 70, QFont.Weight.Black))
    painter.drawText(QRect(25, 28, 206, 112), Qt.AlignmentFlag.AlignCenter, "KR")
    painter.end()
    if not image.save(str(temporary_png), "PNG"):
        raise RuntimeError("could not render icon PNG")

    png = temporary_png.read_bytes()
    icon_header = struct.pack("<HHH", 0, 1, 1)
    icon_entry = struct.pack("<BBBBHHII", 0, 0, 0, 0, 1, 32, len(png), 22)
    (PROJECT / "assets" / "keyrhythm.ico").write_bytes(icon_header + icon_entry + png)
    application.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
