"""Scheda "Cronologia": dork salvati ed esecuzioni precedenti."""

from __future__ import annotations

import time

from ..qtcompat import Qt, QtCore, QtGui, QtWidgets, Signal
from .widgets import Badge, confirm, info_label, message


def _when(timestamp: float) -> str:
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(timestamp))


class HistoryTab(QtWidgets.QWidget):
    """Elenco dei dork salvati e storico delle ricerche eseguite."""

    load_query = Signal(str)
    status = Signal(str)

    def __init__(self, store, parent=None) -> None:
        super().__init__(parent)
        self.store = store

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Cronologia e dork salvati")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.stats_badge = Badge("", "#3d7bff")
        header.addWidget(self.stats_badge)
        layout.addLayout(header)

        splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(self._build_saved())
        splitter.addWidget(self._build_runs())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 4)
        layout.addWidget(splitter, 1)

        self.reload()

    def _build_saved(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Dork salvati")
        layout = QtWidgets.QVBoxLayout(box)

        self.saved_table = QtWidgets.QTableWidget(0, 4)
        self.saved_table.setHorizontalHeaderLabels(["★", "Nome", "Query", "Salvato"])
        self.saved_table.setAlternatingRowColors(True)
        self.saved_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.saved_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.saved_table.verticalHeader().setVisible(False)
        header = self.saved_table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.saved_table.itemDoubleClicked.connect(lambda *_: self._load_saved())
        layout.addWidget(self.saved_table)

        row = QtWidgets.QHBoxLayout()
        load = QtWidgets.QPushButton("Carica nel costruttore")
        load.setObjectName("primary")
        load.clicked.connect(self._load_saved)
        favorite = QtWidgets.QPushButton("Preferito")
        favorite.clicked.connect(self._toggle_favorite)
        delete = QtWidgets.QPushButton("Elimina")
        delete.setObjectName("danger")
        delete.clicked.connect(self._delete_saved)
        row.addWidget(load)
        row.addWidget(favorite)
        row.addStretch(1)
        row.addWidget(delete)
        layout.addLayout(row)
        return box

    def _build_runs(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Ricerche eseguite")
        layout = QtWidgets.QVBoxLayout(box)

        self.runs_table = QtWidgets.QTableWidget(0, 5)
        self.runs_table.setHorizontalHeaderLabels(
            ["Quando", "Motore", "Contesto", "Risultati", "Query"])
        self.runs_table.setAlternatingRowColors(True)
        self.runs_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.runs_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.runs_table.verticalHeader().setVisible(False)
        header = self.runs_table.horizontalHeader()
        for column in range(4):
            header.setSectionResizeMode(
                column, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.runs_table.itemDoubleClicked.connect(lambda *_: self._load_run())
        layout.addWidget(self.runs_table)

        row = QtWidgets.QHBoxLayout()
        reuse = QtWidgets.QPushButton("Riusa la query")
        reuse.clicked.connect(self._load_run)
        clear = QtWidgets.QPushButton("Svuota la cronologia")
        clear.setObjectName("danger")
        clear.clicked.connect(self._clear_runs)
        row.addWidget(reuse)
        row.addStretch(1)
        row.addWidget(clear)
        layout.addLayout(row)
        return box

    # -------------------------------------------------------------------- dati
    def reload(self) -> None:
        saved = self.store.saved_dorks()
        self.saved_table.setRowCount(0)
        for entry in saved:
            row = self.saved_table.rowCount()
            self.saved_table.insertRow(row)
            star = QtWidgets.QTableWidgetItem("★" if entry.favorite else "")
            star.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.saved_table.setItem(row, 0, star)
            self.saved_table.setItem(row, 1, QtWidgets.QTableWidgetItem(entry.name))
            query_item = QtWidgets.QTableWidgetItem(entry.query)
            query_item.setToolTip(entry.query)
            self.saved_table.setItem(row, 2, query_item)
            self.saved_table.setItem(row, 3,
                                     QtWidgets.QTableWidgetItem(_when(entry.created_at)))

        runs = self.store.runs()
        self.runs_table.setRowCount(0)
        for entry in runs:
            row = self.runs_table.rowCount()
            self.runs_table.insertRow(row)
            self.runs_table.setItem(row, 0,
                                    QtWidgets.QTableWidgetItem(_when(entry.created_at)))
            self.runs_table.setItem(row, 1, QtWidgets.QTableWidgetItem(entry.provider))
            self.runs_table.setItem(row, 2, QtWidgets.QTableWidgetItem(entry.context))
            hits = QtWidgets.QTableWidgetItem()
            hits.setData(Qt.ItemDataRole.DisplayRole, entry.hits)
            if entry.error:
                hits.setForeground(QtGui.QBrush(QtGui.QColor("#c0392b")))
                hits.setToolTip(entry.error)
            self.runs_table.setItem(row, 3, hits)
            query_item = QtWidgets.QTableWidgetItem(entry.query)
            query_item.setToolTip(entry.error or entry.query)
            self.runs_table.setItem(row, 4, query_item)

        stats = self.store.stats()
        self.stats_badge.setText(
            "%d salvati · %d ricerche · %d risultati"
            % (stats["salvati"], stats["esecuzioni"], stats["risultati"]))

    # ------------------------------------------------------------------ azioni
    def _selected_saved_id(self) -> int | None:
        rows = {index.row() for index in self.saved_table.selectedIndexes()}
        if not rows:
            return None
        item = self.saved_table.item(sorted(rows)[0], 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _load_saved(self) -> None:
        rows = {index.row() for index in self.saved_table.selectedIndexes()}
        if not rows:
            return
        item = self.saved_table.item(sorted(rows)[0], 2)
        if item:
            self.load_query.emit(item.text())
            self.status.emit("Dork caricato nel costruttore")

    def _toggle_favorite(self) -> None:
        saved_id = self._selected_saved_id()
        if saved_id is not None:
            self.store.toggle_favorite(saved_id)
            self.reload()

    def _delete_saved(self) -> None:
        saved_id = self._selected_saved_id()
        if saved_id is None:
            return
        if confirm(self, "Eliminare il dork", "Il dork salvato verra' rimosso."):
            self.store.delete_saved(saved_id)
            self.reload()

    def _load_run(self) -> None:
        rows = {index.row() for index in self.runs_table.selectedIndexes()}
        if not rows:
            return
        item = self.runs_table.item(sorted(rows)[0], 4)
        if item:
            self.load_query.emit(item.text())
            self.status.emit("Query caricata nel costruttore")

    def _clear_runs(self) -> None:
        if confirm(self, "Svuotare la cronologia",
                   "Tutte le ricerche registrate verranno eliminate. "
                   "I dork salvati non vengono toccati."):
            self.store.clear_runs()
            self.reload()
