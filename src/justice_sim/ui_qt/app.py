"""Qt application entry point."""

from __future__ import annotations

import signal
import sys

from PySide6 import QtCore, QtWidgets

from justice_sim.config import load_builtin_data
from justice_sim.ui_qt.main_window import MainWindow


def create_app() -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv)
    return app


def install_sigint_handler(app: QtWidgets.QApplication) -> QtCore.QTimer:
    def _handle_sigint(*_: object) -> None:
        app.quit()

    signal.signal(signal.SIGINT, _handle_sigint)
    timer = QtCore.QTimer(app)
    timer.setInterval(100)
    timer.timeout.connect(lambda: None)
    timer.start()
    return timer


def main() -> int:
    app = create_app()
    app._sigint_timer = install_sigint_handler(app)
    data = load_builtin_data()
    window = MainWindow(data)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
