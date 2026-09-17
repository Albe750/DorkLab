"""Scheda "Risultati": tabella, sintesi agentica, download ed estrazione."""

from __future__ import annotations

from pathlib import Path

from .. import exporters, metadata as metadata_mod
from ..qtcompat import Qt, QtCore, QtGui, QtWidgets, Signal
from ..providers.base import SearchResult
from .widgets import Badge, choose_directory, confirm, info_label, message
from .workers import DownloadWorker, ExtractWorker

COLUMNS = ["#", "Titolo", "Tipo", "Dominio", "Vincoli", "Estratto"]

COMPLIANCE_COLORS = {
    "ok": "#16a34a",
    "parziale": "#d97706",
    "fuori": "#c0392b",
    "sconosciuto": "#6b7280",
}


class ResultsTab(QtWidgets.QWidget):
    """Mostra i risultati e permette di lavorarci sopra."""

    status = Signal(str)

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.results: list[SearchResult] = []
        self.query = ""
        self.answer = ""
        self._worker = None
        self._extracted: dict[str, str] = {}

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        layout.addLayout(self._build_header())

        self.answer_box = QtWidgets.QGroupBox("Sintesi del motore agentico")
        answer_layout = QtWidgets.QVBoxLayout(self.answer_box)
        self.answer_view = QtWidgets.QTextBrowser()
        self.answer_view.setMaximumHeight(150)
        self.answer_view.setOpenExternalLinks(True)
        answer_layout.addWidget(self.answer_view)
        self.answer_box.setVisible(False)
        layout.addWidget(self.answer_box)

        splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(self._build_table())
        splitter.addWidget(self._build_details())
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        layout.addLayout(self._build_actions())

        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

    # ------------------------------------------------------------- costruzione
    def _build_header(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        self.title = QtWidgets.QLabel("Nessuna ricerca eseguita")
        self.title.setObjectName("sectionTitle")
        row.addWidget(self.title)
        row.addStretch(1)

        self.filter_edit = QtWidgets.QLineEdit()
        self.filter_edit.setPlaceholderText("Filtra i risultati…")
        self.filter_edit.setMaximumWidth(240)
        self.filter_edit.textChanged.connect(self._apply_filter)
        row.addWidget(self.filter_edit)

        self.only_compliant = QtWidgets.QCheckBox("Solo conformi")
        self.only_compliant.setToolTip(
            "Nasconde i risultati che non rispettano i vincoli della query.")
        self.only_compliant.toggled.connect(self._apply_filter)
        row.addWidget(self.only_compliant)
        return row

    def _build_table(self) -> QtWidgets.QWidget:
        self.table = QtWidgets.QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSortingEnabled(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QtWidgets.QHeaderView.ResizeMode.Stretch)

        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.itemDoubleClicked.connect(lambda *_: self.open_selected())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        return self.table

    def _build_details(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QTabWidget()
        self.detail_view = QtWidgets.QTextBrowser()
        self.detail_view.setOpenExternalLinks(True)
        panel.addTab(self.detail_view, "Dettaglio")

        self.metadata_view = QtWidgets.QTextBrowser()
        panel.addTab(self.metadata_view, "Metadati")

        self.content_view = QtWidgets.QPlainTextEdit()
        self.content_view.setReadOnly(True)
        panel.addTab(self.content_view, "Contenuto estratto")
        self.detail_panel = panel
        return panel

    def _build_actions(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        self.open_button = QtWidgets.QPushButton("Apri")
        self.open_button.clicked.connect(self.open_selected)
        self.copy_button = QtWidgets.QPushButton("Copia URL")
        self.copy_button.clicked.connect(self.copy_selected)
        self.download_button = QtWidgets.QPushButton("Scarica selezionati")
        self.download_button.setObjectName("primary")
        self.download_button.clicked.connect(self.download_selected)
        self.extract_button = QtWidgets.QPushButton("Estrazione approfondita")
        self.extract_button.setToolTip(
            "Recupera il testo completo delle pagine selezionate tramite Tavily.")
        self.extract_button.clicked.connect(self.extract_selected)
        self.export_button = QtWidgets.QPushButton("Esporta…")
        self.export_button.clicked.connect(self.export_results)
        self.stop_button = QtWidgets.QPushButton("Interrompi")
        self.stop_button.setObjectName("danger")
        self.stop_button.clicked.connect(self._stop)
        self.stop_button.setVisible(False)

        for widget in (self.open_button, self.copy_button, self.download_button,
                       self.extract_button, self.export_button):
            row.addWidget(widget)
        row.addStretch(1)
        row.addWidget(self.stop_button)
        self._set_actions_enabled(False)
        return row

    # ------------------------------------------------------------------- dati
    def set_response(self, response) -> None:
        """Carica una risposta di ricerca nella tabella."""
        self.results = list(response.results)
        self.query = response.query
        self.answer = response.answer or ""
        self._extracted.clear()

        self.title.setText("%d risultati · %s" % (len(self.results), response.provider))
        self.answer_box.setVisible(bool(self.answer))
        if self.answer:
            self.answer_view.setPlainText(self.answer)

        self._populate()
        self._set_actions_enabled(bool(self.results))
        if response.meta:
            details = " · ".join("%s: %s" % (k, v) for k, v in response.meta.items())
            self.status.emit(details)

    def append_results(self, results: list[SearchResult]) -> None:
        known = {r.url for r in self.results}
        for item in results:
            if item.url not in known:
                self.results.append(item)
                known.add(item.url)
        self.title.setText("%d risultati (uniti)" % len(self.results))
        self._populate()
        self._set_actions_enabled(bool(self.results))

    def _populate(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for index, item in enumerate(self.results, start=1):
            row = self.table.rowCount()
            self.table.insertRow(row)

            number = QtWidgets.QTableWidgetItem()
            number.setData(Qt.ItemDataRole.DisplayRole, index)
            number.setData(Qt.ItemDataRole.UserRole, index - 1)
            self.table.setItem(row, 0, number)

            title = QtWidgets.QTableWidgetItem(item.title or item.url)
            title.setToolTip(item.url)
            self.table.setItem(row, 1, title)
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(item.filetype or "-"))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(item.domain))

            compliance = QtWidgets.QTableWidgetItem(item.compliance)
            color = COMPLIANCE_COLORS.get(item.compliance, "#6b7280")
            compliance.setForeground(QtGui.QBrush(QtGui.QColor(color)))
            if item.checks:
                compliance.setToolTip("\n".join(
                    "%s: %s" % (k, {True: "rispettato", False: "non rispettato",
                                    None: "non verificabile"}[v])
                    for k, v in item.checks.items()))
            self.table.setItem(row, 4, compliance)
            self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(
                " ".join((item.snippet or "").split())[:200]))
        self.table.setSortingEnabled(True)
        self._apply_filter()

    def _apply_filter(self) -> None:
        needle = self.filter_edit.text().strip().lower()
        only_ok = self.only_compliant.isChecked()
        for row in range(self.table.rowCount()):
            item = self._result_at(row)
            if item is None:
                continue
            visible = True
            if needle:
                haystack = " ".join((item.title, item.url, item.snippet,
                                     item.domain)).lower()
                visible = needle in haystack
            if visible and only_ok and item.compliance == "fuori":
                visible = False
            self.table.setRowHidden(row, not visible)

    def _result_at(self, row: int) -> SearchResult | None:
        cell = self.table.item(row, 0)
        if cell is None:
            return None
        index = cell.data(Qt.ItemDataRole.UserRole)
        if index is None or index >= len(self.results):
            return None
        return self.results[index]

    def selected_results(self) -> list[SearchResult]:
        rows = {index.row() for index in self.table.selectedIndexes()}
        items = [self._result_at(row) for row in sorted(rows)]
        return [item for item in items if item is not None]

    # ---------------------------------------------------------------- azioni
    def _selection_changed(self) -> None:
        chosen = self.selected_results()
        if not chosen:
            self.detail_view.clear()
            return
        item = chosen[0]
        checks = "".join(
            "<li>%s: <b>%s</b></li>" % (k, {True: "rispettato", False: "non rispettato",
                                            None: "non verificabile"}[v])
            for k, v in (item.checks or {}).items())
        self.detail_view.setHtml(
            "<h3>%s</h3><p><a href='%s'>%s</a></p>"
            "<p><b>Dominio:</b> %s &middot; <b>Tipo:</b> %s &middot; "
            "<b>Motore:</b> %s</p>"
            "<p>%s</p>%s"
            % (_esc(item.title or item.url), _esc(item.url), _esc(item.url),
               _esc(item.domain), _esc(item.filetype or "-"), _esc(item.provider),
               _esc(item.snippet or ""),
               ("<p><b>Verifica dei vincoli</b></p><ul>%s</ul>" % checks) if checks else "")
        )
        content = self._extracted.get(item.url, "")
        self.content_view.setPlainText(content or "Nessun contenuto estratto per questo URL.")

    def _context_menu(self, point) -> None:
        if not self.selected_results():
            return
        menu = QtWidgets.QMenu(self)
        open_action = menu.addAction("Apri nel browser")
        copy_action = menu.addAction("Copia URL")
        copy_all = menu.addAction("Copia tutti gli URL visibili")
        menu.addSeparator()
        download = menu.addAction("Scarica selezionati")
        extract = menu.addAction("Estrazione approfondita")

        chosen = menu.exec(self.table.viewport().mapToGlobal(point))
        if chosen is open_action:
            self.open_selected()
        elif chosen is copy_action:
            self.copy_selected()
        elif chosen is copy_all:
            urls = [self._result_at(row).url for row in range(self.table.rowCount())
                    if not self.table.isRowHidden(row) and self._result_at(row)]
            QtWidgets.QApplication.clipboard().setText("\n".join(urls))
            self.status.emit("Copiati %d URL" % len(urls))
        elif chosen is download:
            self.download_selected()
        elif chosen is extract:
            self.extract_selected()

    def open_selected(self) -> None:
        chosen = self.selected_results()
        if not chosen:
            return
        if len(chosen) > 5 and not confirm(
                self, "Molte schede",
                "Stai per aprire %d schede del browser. Procedo?" % len(chosen)):
            return
        for item in chosen:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(item.url))

    def copy_selected(self) -> None:
        chosen = self.selected_results()
        if chosen:
            QtWidgets.QApplication.clipboard().setText(
                "\n".join(item.url for item in chosen))
            self.status.emit("Copiati %d URL" % len(chosen))

    def download_selected(self) -> None:
        chosen = self.selected_results()
        if not chosen:
            message(self, "Nessuna selezione", "Seleziona almeno un risultato.", "warn")
            return
        # scelta interattiva della cartella: parte da quella predefinita
        destination = choose_directory(
            self, self.config.download_path(),
            "Dove salvare %d file" % len(chosen))
        if not destination:
            return                       # annullato dall'utente
        # ricorda la scelta per la volta successiva
        self.config.set("download_dir", destination)
        try:
            self.config.save()
        except OSError:
            pass

        self._download_dir = destination
        self._begin_work("Download in corso", len(chosen))
        self._worker = DownloadWorker([item.url for item in chosen], self.config,
                                      directory=destination)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished_all.connect(self._on_download_done)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.start()

    def extract_selected(self) -> None:
        chosen = self.selected_results()
        if not chosen:
            message(self, "Nessuna selezione", "Seleziona almeno un risultato.", "warn")
            return
        if not self.config.credential("tavily_api_key"):
            message(self, "Tavily non configurato",
                    "L'estrazione approfondita usa l'endpoint /extract di Tavily.\n"
                    "Inserisci la chiave in Impostazioni → Motori.", "warn")
            return

        self._begin_work("Estrazione del contenuto", 0)
        self._worker = ExtractWorker([item.url for item in chosen], self.config)
        self._worker.progress.connect(lambda text: self.status.emit(text))
        self._worker.finished_ok.connect(self._on_extract_done)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.start()

    def export_results(self) -> None:
        if not self.results:
            return
        path, selected = QtWidgets.QFileDialog.getSaveFileName(
            self, "Esporta i risultati", str(Path.home() / "dorklab-risultati.csv"),
            "CSV (*.csv);;JSON (*.json);;Markdown (*.md);;HTML (*.html)")
        if not path:
            return
        suffix = Path(path).suffix.lower()
        try:
            if suffix == ".json":
                exporters.results_to_json(self.results, path, self.query)
            elif suffix == ".md":
                exporters.results_to_markdown(self.results, path, self.query, self.answer)
            elif suffix == ".html":
                exporters.results_to_html(self.results, path, self.query, self.answer)
            else:
                exporters.results_to_csv(self.results, path)
        except OSError as exc:
            message(self, "Esportazione non riuscita", str(exc), "error")
            return
        self.status.emit("Esportato in %s" % path)

    # ------------------------------------------------------------- avanzamento
    def _begin_work(self, label: str, total: int) -> None:
        self.progress.setVisible(True)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.progress.setFormat(label + " — %p%")
        if total == 0:
            self.progress.setRange(0, 0)
        self.stop_button.setVisible(True)
        self._set_actions_enabled(False)

    def _end_work(self) -> None:
        self.progress.setVisible(False)
        self.stop_button.setVisible(False)
        self._set_actions_enabled(bool(self.results))
        self._worker = None

    def _on_progress(self, index: int, total: int, url: str) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(index)
        self.status.emit("%d/%d  %s" % (index, total, url[:90]))

    def _on_download_done(self, outcomes, metadata_entries) -> None:
        ok = [o for o in outcomes if o.ok]
        failed = [o for o in outcomes if not o.ok]
        self._end_work()

        if metadata_entries:
            self._show_metadata(metadata_entries)
        summary = "Scaricati %d file su %d." % (len(ok), len(outcomes))
        if failed:
            summary += "\n\nNon riusciti:\n" + "\n".join(
                "• %s — %s" % (o.url[:70], o.reason) for o in failed[:10])
        message(self, "Download completato", summary,
                "info" if ok else "warn")
        self.status.emit("Download: %d/%d in %s"
                         % (len(ok), len(outcomes), self.config.download_path()))

    def _show_metadata(self, entries: list[dict]) -> None:
        summary = metadata_mod.summarize(entries)
        parts = ["<h3>Metadati estratti da %d documenti</h3>" % len(entries)]
        for bucket, values in summary.items():
            parts.append("<p><b>%s</b></p><ul>%s</ul>" % (
                _esc(bucket),
                "".join("<li>%s <i>(%d)</i></li>" % (_esc(name), count)
                        for name, count in values[:12])))
        parts.append("<h4>Dettaglio per file</h4>")
        for entry in entries[:60]:
            rows = "".join("<li>%s: %s</li>" % (_esc(k), _esc(str(v)))
                           for k, v in entry.items() if k not in {"file", "url"})
            parts.append("<p><b>%s</b></p><ul>%s</ul>"
                         % (_esc(Path(entry.get("file", "")).name), rows))
        self.metadata_view.setHtml("".join(parts))
        self.detail_panel.setCurrentIndex(1)

    def _on_extract_done(self, content: dict) -> None:
        self._extracted.update(content)
        self._end_work()
        non_empty = sum(1 for value in content.values() if value)
        self.status.emit("Contenuto estratto per %d/%d URL" % (non_empty, len(content)))
        self.detail_panel.setCurrentIndex(2)
        self._selection_changed()

    def _on_worker_failed(self, error: str) -> None:
        self._end_work()
        message(self, "Operazione non riuscita", error, "error")

    def _stop(self) -> None:
        if self._worker and hasattr(self._worker, "stop"):
            self._worker.stop()
            self.status.emit("Interruzione richiesta…")

    def _set_actions_enabled(self, enabled: bool) -> None:
        for widget in (self.open_button, self.copy_button, self.download_button,
                       self.extract_button, self.export_button):
            widget.setEnabled(enabled)


def _esc(text: str) -> str:
    import html

    return html.escape(text or "")
