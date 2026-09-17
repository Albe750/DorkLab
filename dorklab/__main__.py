"""Avvio dell'applicazione: python -m dorklab (oppure il comando dorklab)."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from .qtcompat import QtGui, QtWidgets
    except ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    from . import APP_ID, APP_NAME
    from .ui import MainWindow

    QtWidgets.QApplication.setApplicationName(APP_NAME)
    QtWidgets.QApplication.setApplicationDisplayName(APP_NAME)
    QtWidgets.QApplication.setDesktopFileName(APP_ID)

    application = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
