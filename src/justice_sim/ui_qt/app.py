"""Qt application entry point."""

from __future__ import annotations

import argparse
import signal
import sys

from PySide6 import QtCore, QtWidgets

from justice_sim.config import load_builtin_data, load_builtin_suggested_rules
from justice_sim.ui_qt.main_window import MainWindow
from justice_sim.ui_qt.ui_scale import UI_SCALE_MODES


def create_app(argv: list[str] | None = None) -> QtWidgets.QApplication:
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication(sys.argv if argv is None else argv)
    app.setOrganizationName("JusticeMonumentSimulator")
    app.setApplicationName("JusticeMonumentSimulator")
    app.setApplicationDisplayName("Justice Monument Simulator")
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Justice Monument Simulator (GUI)")
    parser.add_argument(
        "--theme",
        choices=("light", "dark"),
        help="Override the saved theme for this launch.",
    )
    parser.add_argument(
        "--ui-scale",
        choices=UI_SCALE_MODES,
        help="Override the saved UI scale mode for this launch.",
    )
    parser.add_argument(
        "--prompt-tour",
        action="store_true",
        help="Always prompt the guided tour on launch.",
    )
    args, remaining = parser.parse_known_args(argv)

    qt_argv = [sys.argv[0]] + remaining if remaining is not None else None
    app = create_app(qt_argv)
    app._sigint_timer = install_sigint_handler(app)
    data = load_builtin_data()
    suggested_rules = load_builtin_suggested_rules(data)
    theme_override = None
    if args.theme == "dark":
        theme_override = True
    elif args.theme == "light":
        theme_override = False
    window = MainWindow(
        data,
        suggested_rules=suggested_rules,
        theme_override=theme_override,
        ui_scale_override=args.ui_scale,
        prompt_tour=args.prompt_tour,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
