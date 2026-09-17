"""Livello di compatibilita' tra PyQt6 e PySide6.

Fedora distribuisce entrambi i binding (python3-pyqt6, python3-pyside6).
DorkLab usa il primo disponibile, cosi' l'utente non e' costretto a
installare un binding specifico.
"""

from __future__ import annotations

QT_API = ""

try:  # pragma: no cover - dipende dall'ambiente
    from PyQt6 import QtCore, QtGui, QtWidgets  # type: ignore
    from PyQt6.QtCore import pyqtSignal as Signal  # type: ignore
    from PyQt6.QtCore import pyqtSlot as Slot  # type: ignore

    QT_API = "PyQt6"
except ImportError:  # pragma: no cover - dipende dall'ambiente
    try:
        from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore
        from PySide6.QtCore import Signal, Slot  # type: ignore

        QT_API = "PySide6"
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Nessun binding Qt trovato. Su Fedora installa uno dei due:\n"
            "  sudo dnf install python3-pyqt6\n"
            "  sudo dnf install python3-pyside6\n"
            "oppure: pip install PyQt6"
        ) from exc

Qt = QtCore.Qt

__all__ = ["QtCore", "QtGui", "QtWidgets", "Qt", "Signal", "Slot", "QT_API"]
