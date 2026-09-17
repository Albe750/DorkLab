"""Scheda "GHDB": catalogo di dork difensivi consultabile e importabile."""

from __future__ import annotations

from pathlib import Path

from .. import catalog, ghdb
from ..qtcompat import Qt, QtCore, QtGui, QtWidgets, Signal
from .widgets import Badge, BubbleBar, info_label, message


class GhdbTab(QtWidgets.QWidget):
    """Consultazione del catalogo in stile Google Hacking Database."""

    load_in_builder = Signal(str)
    use_for_audit = Signal(str)
    status = Signal(str)

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._entries: list[ghdb.GhdbEntry] = []
        self._category = ""
        self._severity = ""

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        intro = info_label(
            "Catalogo di ricerche note per individuare esposizioni accidentali, "
            "organizzato secondo la tassonomia della Google Hacking Database. "
            "Usale sul tuo dominio: dalla scheda Audit ogni voce viene "
            "automaticamente vincolata al perimetro autorizzato.")
        layout.addWidget(intro)

        layout.addLayout(self._build_filters())

        splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._build_table())
        splitter.addWidget(self._build_detail())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        layout.addLayout(self._build_actions())
        self.reload()

    # ------------------------------------------------------------- costruzione
    def _build_filters(self) -> QtWidgets.QVBoxLayout:
        box = QtWidgets.QVBoxLayout()

        row = QtWidgets.QHBoxLayout()
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText(
            "Cerca nel catalogo: password, index of, backup…")
        self.search_edit.textChanged.connect(self.reload)
        row.addWidget(self.search_edit, 1)
        self.count_badge = Badge("0 voci", "#3d7bff")
        row.addWidget(self.count_badge)
        box.addLayout(row)

        self.category_bar = BubbleBar()
        self.category_bar.add("Tutte", "", checkable=True)
        for category in ghdb.categories():
            self.category_bar.add(category["label"], category["id"],
                                  tooltip=category["desc"], checkable=True)
        self.category_bar.bubbles()[0].setChecked(True)
        self.category_bar.clicked.connect(self._pick_category)
        box.addWidget(self.category_bar)

        self.severity_bar = BubbleBar()
        self.severity_bar.add("Qualsiasi gravita'", "", checkable=True)
        for name in ("critica", "alta", "media", "info"):
            self.severity_bar.add(catalog.severities()[name]["label"], name,
                                  checkable=True)
        self.severity_bar.bubbles()[0].setChecked(True)
        self.severity_bar.clicked.connect(self._pick_severity)
        box.addWidget(self.severity_bar)
        return box

    def _build_table(self) -> QtWidgets.QWidget:
        self.table = QtWidgets.QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Gravita'", "Categoria", "Titolo", "Dork"])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self.table.itemDoubleClicked.connect(lambda *_: self._load())
        return self.table

    def _build_detail(self) -> QtWidgets.QWidget:
        self.detail = QtWidgets.QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        return self.detail

    def _build_actions(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        load = QtWidgets.QPushButton("Carica nel costruttore")
        load.setObjectName("primary")
        load.clicked.connect(self._load)
        audit = QtWidgets.QPushButton("Usa per l'audit del mio dominio")
        audit.clicked.connect(self._to_audit)
        copy = QtWidgets.QPushButton("Copia dork")
        copy.clicked.connect(self._copy)
        import_button = QtWidgets.QPushButton("Importa catalogo…")
        import_button.setToolTip(
            "Importa voci aggiuntive da un file JSON o CSV (per esempio un "
            "export della GHDB o un elenco interno).")
        import_button.clicked.connect(self._import)
        row.addWidget(load)
        row.addWidget(audit)
        row.addWidget(copy)
        row.addStretch(1)
        row.addWidget(import_button)
        return row

    # ------------------------------------------------------------------- dati
    def _pick_category(self, category_id) -> None:
        self._category = category_id or ""
        for bubble in self.category_bar.bubbles():
            bubble.setChecked(bubble.text() == self.sender_label(category_id))
        self.reload()

    def sender_label(self, category_id) -> str:
        if not category_id:
            return "Tutte"
        return ghdb.category_label(category_id)

    def _pick_severity(self, severity) -> None:
        self._severity = severity or ""
        target = catalog.severities()[severity]["label"] if severity else "Qualsiasi gravita'"
        for bubble in self.severity_bar.bubbles():
            bubble.setChecked(bubble.text() == target)
        self.reload()

    def reload(self) -> None:
        self._entries = ghdb.search(self.search_edit.text(), self._category, self._severity)
        self.count_badge.setText("%d voci" % len(self._entries))

        self.table.setRowCount(0)
        colors = catalog.severities()
        for entry in self._entries:
            row = self.table.rowCount()
            self.table.insertRow(row)

            severity_item = QtWidgets.QTableWidgetItem(
                colors.get(entry.severity, {}).get("label", entry.severity))
            color = colors.get(entry.severity, {}).get("color", "#6b7280")
            severity_item.setForeground(QtGui.QBrush(QtGui.QColor(color)))
            severity_item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.table.setItem(row, 0, severity_item)
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(
                ghdb.category_label(entry.category)))
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(entry.title))
            dork_item = QtWidgets.QTableWidgetItem(entry.dork)
            dork_item.setToolTip(entry.dork)
            self.table.setItem(row, 3, dork_item)

    def current_entry(self) -> ghdb.GhdbEntry | None:
        rows = {index.row() for index in self.table.selectedIndexes()}
        if not rows:
            return None
        row = sorted(rows)[0]
        if row >= len(self._entries):
            return None
        return self._entries[row]

    def _show_detail(self) -> None:
        entry = self.current_entry()
        if entry is None:
            self.detail.clear()
            return
        colors = catalog.severities()
        color = colors.get(entry.severity, {}).get("color", "#6b7280")
        self.detail.setHtml(
            "<h3>%s</h3>"
            "<p><span style='color:%s;font-weight:600'>%s</span> &middot; %s</p>"
            "<pre style='white-space:pre-wrap'>%s</pre>"
            "<p>%s</p>"
            "<p><b>Come rimediare</b><br>%s</p>"
            "<p style='color:#6b7280'>Fonte: %s &middot; id %s</p>"
            % (_esc(entry.title), color,
               _esc(colors.get(entry.severity, {}).get("label", entry.severity)),
               _esc(ghdb.category_label(entry.category)),
               _esc(entry.dork), _esc(entry.note),
               _esc(entry.remediation) or "—", _esc(entry.source), _esc(entry.id))
        )

    # ---------------------------------------------------------------- azioni
    def _load(self) -> None:
        entry = self.current_entry()
        if entry:
            self.load_in_builder.emit(entry.dork)
            self.status.emit("Dork caricato nel costruttore")

    def _to_audit(self) -> None:
        entry = self.current_entry()
        if entry:
            self.use_for_audit.emit(entry.dork)

    def _copy(self) -> None:
        entry = self.current_entry()
        if entry:
            QtWidgets.QApplication.clipboard().setText(entry.dork)
            self.status.emit("Dork copiato")

    def _import(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Importa un catalogo di dork", str(Path.home()),
            "Cataloghi (*.json *.csv);;JSON (*.json);;CSV (*.csv)")
        if not path:
            return
        try:
            entries = ghdb.import_file(path)
        except Exception as exc:  # noqa: BLE001 - file arbitrario
            message(self, "Importazione non riuscita", str(exc), "error")
            return
        if not entries:
            message(self, "Nessuna voce",
                    "Il file non contiene voci riconoscibili. Servono almeno le "
                    "colonne 'dork' (o 'query') e 'title'.", "warn")
            return
        added = ghdb.merge_user_entries(entries)
        self.reload()
        message(self, "Importazione completata",
                "Voci lette: %d\nNuove aggiunte: %d" % (len(entries), added))


def _esc(text: str) -> str:
    import html

    return html.escape(text or "")
