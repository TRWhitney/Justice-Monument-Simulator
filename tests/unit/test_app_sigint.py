import os
import signal

import pytest

from justice_sim.ui_qt.app import create_app, install_sigint_handler


@pytest.mark.unit
def test_install_sigint_handler_sets_timer_and_handler():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = create_app()
    previous = signal.getsignal(signal.SIGINT)
    timer = install_sigint_handler(app)
    try:
        assert signal.getsignal(signal.SIGINT) is not previous
        assert timer.isActive()
    finally:
        signal.signal(signal.SIGINT, previous)
        timer.stop()
