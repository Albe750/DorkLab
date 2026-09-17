"""Finestra: tecnologia rilevata del sito e dork suggeriti."""

from __future__ import annotations

from ..qtcompat import Qt, QtWidgets, Signal
from .widgets import Badge, info_label


class FingerprintDialog(QtWidgets.QDialog):
    """Mostra le tecnologie rilevate e i dork adatti, con azioni rapide."""

    load_in_builder = Signal(str)         # query da caricare nel costruttore

    def __init__(self, report, parent=None) -> None:
        super().__init__(parent)
        self.report = report
        self.setWindowTitle("Fingerprint e dork — %s" % report.domain)
        self.setMinimumSize(720, 560)

        layout = QtWidgets.QVBoxLayout(self)

        title = QtWidgets.QLabel("Tecnologia rilevata")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        if report.found:
            badges = QtWidgets.QHBoxLayout()
            badges.setSpacing(6)
            for match in report.matches:
                badge = Badge(match.label, match.color)
                badge.setToolTip("\n".join(match.evidence))
                badges.addWidget(badge)
            badges.addStretch(1)
            layout.addLayout(badges)

            evidence = "; ".join(
                "%s (%s)" % (m.label, ", ".join(m.evidence[:3])) for m in report.matches)
            layout.addWidget(info_label("Indizi: " + evidence))
        else:
            layout.addWidget(info_label(
                "Nessuna tecnologia riconosciuta con certezza. Vengono comunque "
                "proposti i dork generici piu' utili."))

        server = report.headers.get("Server") or report.headers.get("server")
        powered = report.headers.get("X-Powered-By") or report.headers.get("x-powered-by")
        if server or powered:
            layout.addWidget(info_label(
                "Intestazioni del server: "
                + ", ".join(filter(None, ["Server: %s" % server if server else "",
                                          "X-Powered-By: %s" % powered if powered else ""]))))

        dork_title = QtWidgets.QLabel("Dork suggeriti")
        dork_title.setObjectName("sectionTitle")
        layout.addWidget(dork_title)
        layout.addWidget(info_label(
            "Doppio clic o «Carica» porta il dork nel Costruttore, dove puoi "
            "eseguirlo con il motore scelto o aprirlo nel browser."))

        self.table = QtWidgets.QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Tecnologia", "Cosa cerca", "Dork"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.itemDoubleClicked.connect(lambda *_: self._load())

        self._dorks = report.dorks()
        for dork in self._dorks:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(dork.tech))
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(dork.label))
            item = QtWidgets.QTableWidgetItem(dork.query)
            item.setToolTip(dork.query)
            self.table.setItem(row, 2, item)
        layout.addWidget(self.table, 1)

        buttons = QtWidgets.QHBoxLayout()
        load = QtWidgets.QPushButton("Carica nel Costruttore")
        load.setObjectName("primary")
        load.clicked.connect(self._load)
        copy = QtWidgets.QPushButton("Copia dork")
        copy.clicked.connect(self._copy)
        copy_all = QtWidgets.QPushButton("Copia tutti")
        copy_all.clicked.connect(self._copy_all)
        close = QtWidgets.QPushButton("Chiudi")
        close.clicked.connect(self.accept)
        buttons.addWidget(load)
        buttons.addWidget(copy)
        buttons.addWidget(copy_all)
        buttons.addStretch(1)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _current(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        if not rows:
            return None
        row = sorted(rows)[0]
        return self._dorks[row] if row < len(self._dorks) else None

    def _load(self) -> None:
        dork = self._current()
        if dork:
            self.load_in_builder.emit(dork.query)
            self.accept()

    def _copy(self) -> None:
        dork = self._current()
        if dork:
            QtWidgets.QApplication.clipboard().setText(dork.query)

    def _copy_all(self) -> None:
        QtWidgets.QApplication.clipboard().setText(
            "\n".join(d.query for d in self._dorks))
