from __future__ import annotations

import sys

from keyrhythm import __version__
from keyrhythm.config import AppPaths
from keyrhythm.logging_config import configure_logging


def main(argv: list[str] | None = None) -> int:
    paths = AppPaths.discover()
    paths.ensure()
    configure_logging(paths.logs)
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is not installed. Install KeyRhythm with the 'app' extra.", file=sys.stderr)
        return 2
    from keyrhythm.ui.main_window import MainWindow
    from keyrhythm.ui.theme import apply_theme

    application = QApplication(argv if argv is not None else sys.argv)
    application.setApplicationName("KeyRhythm")
    application.setApplicationDisplayName("KeyRhythm")
    application.setApplicationVersion(__version__)
    application.setOrganizationName("KeyRhythm")
    apply_theme(application)
    window = MainWindow()
    window.resize(1100, 720)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
