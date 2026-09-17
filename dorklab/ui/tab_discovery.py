"""Scheda "Scoperta": contenuto non indicizzato dai motori di ricerca.

E' il cuore dello strumento: i motori indicizzano solo una frazione di cio' che
e' pubblico. Qui si pesca il resto - archivi storici, sitemap, directory aperte,
sottodomini dimenticati - e, per il proprio dominio, si sondano attivamente i
percorsi tipici delle esposizioni.
"""

from __future__ import annotations

from pathlib import Path

from .. import audit, catalog, discovery, exporters
from ..qtcompat import Qt, QtCore, QtGui, QtWidgets, Signal
from .widgets import Badge, BubbleBar, confirm, info_label, message
from .workers import DiscoveryWorker, DownloadWorker


class DiscoveryTab(QtWidgets.QWidget):
    """Scoperta di URL non indicizzati e recupero del loro contenuto."""

    status = Signal(str)
    send_to_results = Signal(list)        # list[SearchResult]

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._items: list[discovery.DiscoveredUrl] = []
        self._source_bubbles: dict = {}
        self._filetype_bubbles: dict = {}
        self._worker: DiscoveryWorker | None = None
        self._download_worker: DownloadWorker | None = None
        self._pending = 0

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        layout.addWidget(info_label(
            "I motori indicizzano solo una parte del web pubblico. Qui trovi il "
            "resto: URL storici in archivio (anche pagine non piu' online), "
            "sitemap e robots.txt, directory aperte, sottodomini dai log dei "
            "certificati. Il sondaggio attivo dei percorsi, che interroga il "
            "server, richiede l'autorizzazione sul dominio."))

        layout.addWidget(self._build_target())
        layout.addWidget(self._build_sources())

        splitter = QtWidgets.QSplitter(Qt.Orientation.Vertical, self)
        splitter.addWidget(self._build_table())
        splitter.setStretchFactor(0, 1)
        layout.addWidget(splitter, 1)

        layout.addLayout(self._build_actions())
        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self._update_state()

    # ------------------------------------------------------------- bersaglio
    def _build_target(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Dominio")
        layout = QtWidgets.QVBoxLayout(box)

        row = QtWidgets.QHBoxLayout()
        self.domain_edit = QtWidgets.QLineEdit()
        self.domain_edit.setPlaceholderText("esempio.it")
        self.domain_edit.textChanged.connect(self._update_state)
        self.domain_edit.returnPressed.connect(self.run_discovery)
        row.addWidget(self.domain_edit, 1)
        self.domain_badge = Badge("nessun dominio", "#6b7280")
        row.addWidget(self.domain_badge)

        row.addWidget(QtWidgets.QLabel("Max"))
        self.limit_spin = QtWidgets.QSpinBox()
        self.limit_spin.setRange(20, 20000)
        self.limit_spin.setSingleStep(100)
        self.limit_spin.setValue(1000)
        self.limit_spin.setToolTip("Numero massimo di URL per fonte.")
        row.addWidget(self.limit_spin)
        layout.addLayout(row)

        self.authorized = QtWidgets.QCheckBox(
            "Sono proprietario di questo dominio o ho un'autorizzazione scritta "
            "a verificarlo (necessario per il sondaggio attivo dei percorsi).")
        self.authorized.toggled.connect(self._update_state)
        layout.addWidget(self.authorized)
        return box

    def _build_sources(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Fonti e filtri")
        layout = QtWidgets.QVBoxLayout(box)

        for kind in discovery.kinds():
            sources = discovery.by_kind(kind)
            if not sources:
                continue
            label = QtWidgets.QLabel(discovery.KIND_LABELS[kind])
            label.setObjectName("hint")
            label.setToolTip(discovery.KIND_HELP[kind])
            layout.addWidget(label)

            bar = BubbleBar()
            for source in sources:
                tooltip = "%s\n\n%s" % (source.description, discovery.KIND_HELP[kind])
                bubble = bar.add(source.label, source.id, tooltip=tooltip,
                                 checkable=True,
                                 sensitive=source.requires_authorization)
                if kind == discovery.ARCHIVE:
                    bubble.setChecked(True)
                self._source_bubbles[source.id] = bubble
            bar.clicked.connect(lambda *_: self._update_state())
            layout.addWidget(bar)

        ft_label = QtWidgets.QLabel("Limita ai tipi di documento (facoltativo)")
        ft_label.setObjectName("hint")
        layout.addWidget(ft_label)
        self.filetype_bar = BubbleBar()
        for group in catalog.filetype_groups():
            bubble = self.filetype_bar.add(group["label"], group["id"],
                                           tooltip=", ".join(group["extensions"]),
                                           checkable=True,
                                           sensitive=group.get("sensitive", False))
            self._filetype_bubbles[group["id"]] = bubble
        layout.addWidget(self.filetype_bar)
        return box

    def _build_table(self) -> QtWidgets.QWidget:
        self.table = QtWidgets.QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Fonte", "URL", "Tipo", "Snapshot", "Stato", "Archivio"])
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
        for column in (2, 3, 4, 5):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemDoubleClicked.connect(lambda *_: self._open_selected())
        return self.table

    def _build_actions(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        self.run_button = QtWidgets.QPushButton("Scopri")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.run_discovery)

        self.prefer_archive = QtWidgets.QCheckBox("Scarica dalla copia archiviata")
        self.prefer_archive.setToolTip(
            "Quando disponibile, scarica lo snapshot dell'archivio invece del vivo: "
            "recupera anche i documenti non piu' online.")

        self.download_button = QtWidgets.QPushButton("Scarica selezionati")
        self.download_button.clicked.connect(self._download_selected)
        self.send_button = QtWidgets.QPushButton("Invia ai Risultati")
        self.send_button.setToolTip(
            "Sposta gli URL selezionati nella scheda Risultati per il download e "
            "l'estrazione dei metadati.")
        self.send_button.clicked.connect(self._send_selected)
        self.export_button = QtWidgets.QPushButton("Esporta\u2026")
        self.export_button.clicked.connect(self._export)
        self.stop_button = QtWidgets.QPushButton("Interrompi")
        self.stop_button.setObjectName("danger")
        self.stop_button.clicked.connect(self._stop)
        self.stop_button.setVisible(False)

        row.addWidget(self.run_button)
        row.addWidget(self.prefer_archive)
        row.addWidget(self.download_button)
        row.addWidget(self.send_button)
        row.addWidget(self.export_button)
        row.addStretch(1)
        self.count_badge = Badge("0 URL", "#3d7bff")
        row.addWidget(self.count_badge)
        row.addWidget(self.stop_button)
        self._set_actions_enabled(False)
        return row

    # ---------------------------------------------------------------- stato
    def _update_state(self) -> None:
        domain = self.domain_edit.text()
        valid = audit.is_valid_domain(domain)
        normalized = audit.normalize_domain(domain)
        if not domain.strip():
            self.domain_badge.setText("nessun dominio"); self.domain_badge.set_color("#6b7280")
        elif valid:
            self.domain_badge.setText(normalized); self.domain_badge.set_color("#16a34a")
        else:
            self.domain_badge.setText("non valido"); self.domain_badge.set_color("#c0392b")

        # le fonti che richiedono autorizzazione seguono la spunta
        for source in discovery.all_sources():
            if source.requires_authorization:
                bubble = self._source_bubbles[source.id]
                bubble.setEnabled(self.authorized.isChecked())
                if not self.authorized.isChecked():
                    bubble.setChecked(False)

        chosen = self._selected_sources()
        self.run_button.setEnabled(valid and bool(chosen))
        self.run_button.setToolTip(
            "" if (valid and chosen) else "Inserisci un dominio valido e scegli almeno una fonte.")

    def _selected_sources(self) -> list[str]:
        return [sid for sid, bubble in self._source_bubbles.items()
                if bubble.isChecked() and bubble.isEnabled()]

    def _selected_filetypes(self) -> list[str]:
        extensions: list[str] = []
        for group_id, bubble in self._filetype_bubbles.items():
            if bubble.isChecked():
                group = catalog.filetype_group(group_id)
                for ext in (group["extensions"] if group else []):
                    if ext not in extensions:
                        extensions.append(ext)
        return extensions

    # ------------------------------------------------------------- esecuzione
    def run_discovery(self) -> None:
        sources = self._selected_sources()
        domain = audit.normalize_domain(self.domain_edit.text())
        if not sources or not audit.is_valid_domain(domain):
            return

        active = [discovery.get(s) for s in sources]
        touching = [s.label for s in active if s and s.touches_target]
        if touching and not confirm(
                self, "Fonti che interrogano il server",
                "Queste fonti leggono direttamente da %s:\n\n%s\n\n"
                "Verranno rispettati robots.txt e il ritardo configurato. Procedo?"
                % (domain, "\n".join("\u2022 " + name for name in touching))):
            return

        self._items = []
        self.table.setRowCount(0)
        self._pending = len(sources)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.stop_button.setVisible(True)
        self.run_button.setEnabled(False)
        self._set_actions_enabled(False)

        self._worker = DiscoveryWorker(
            sources, domain, self.config, limit=self.limit_spin.value(),
            filetypes=self._selected_filetypes(),
            authorized=self.authorized.isChecked())
        self._worker.progress.connect(lambda text: self.status.emit(text))
        self._worker.one_done.connect(self._on_source_done)
        self._worker.one_failed.connect(self._on_source_failed)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()

    def _on_source_done(self, source_id: str, response) -> None:
        before = len(self._items)
        known = {i.url.rstrip("/").lower() for i in self._items}
        for item in response.urls:
            key = item.url.rstrip("/").lower()
            if key and key not in known:
                self._items.append(item)
                known.add(key)
        added = len(self._items) - before
        self._append_rows(response.urls, known_before=before)
        note = response.note or ""
        self.status.emit("%s: +%d URL%s"
                         % (discovery.get(source_id).label, added,
                            " \u2014 " + note if note else ""))

    def _on_source_failed(self, source_id: str, error: str) -> None:
        source = discovery.get(source_id)
        self.status.emit("%s: %s" % (source.label if source else source_id, error))

    def _on_finished(self) -> None:
        self.progress.setVisible(False)
        self.stop_button.setVisible(False)
        self.run_button.setEnabled(True)
        self._worker = None
        self._rebuild_table()
        self.count_badge.setText("%d URL" % len(self._items))
        self._set_actions_enabled(bool(self._items))
        with_archive = sum(1 for i in self._items if i.has_archive)
        self.status.emit("Scoperta completata: %d URL unici (%d con copia archiviata)"
                         % (len(self._items), with_archive))
        if not self._items:
            message(self, "Nessun risultato",
                    "Le fonti selezionate non hanno restituito URL per questo "
                    "dominio. Prova ad aggiungere l'archivio Wayback o i sitemap.",
                    "info")

    def _append_rows(self, urls, known_before) -> None:
        # ricostruzione completa: mantiene ordinamento e deduplica in modo semplice
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for item in self._items:
            row = self.table.rowCount()
            self.table.insertRow(row)
            source = discovery.get(item.source)
            self.table.setItem(row, 0, QtWidgets.QTableWidgetItem(
                source.label.split(" (")[0] if source else item.source))
            url_item = QtWidgets.QTableWidgetItem(item.url)
            url_item.setToolTip(item.url)
            url_item.setData(Qt.ItemDataRole.UserRole, self._items.index(item))
            self.table.setItem(row, 1, url_item)
            self.table.setItem(row, 2, QtWidgets.QTableWidgetItem(item.filetype or "-"))
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(
                _fmt_ts(item.timestamp)))
            status_item = QtWidgets.QTableWidgetItem(item.status or "-")
            if item.status in ("401", "403"):
                status_item.setForeground(QtGui.QBrush(QtGui.QColor("#d97706")))
            self.table.setItem(row, 4, status_item)
            self.table.setItem(row, 5, QtWidgets.QTableWidgetItem(
                "\u2713" if item.has_archive else ""))
        self.table.setSortingEnabled(True)

    def _selected_items(self) -> list:
        rows = {index.row() for index in self.table.selectedIndexes()}
        chosen = []
        for row in sorted(rows):
            cell = self.table.item(row, 1)
            if cell is None:
                continue
            idx = cell.data(Qt.ItemDataRole.UserRole)
            if idx is not None and idx < len(self._items):
                chosen.append(self._items[idx])
        return chosen

    # ---------------------------------------------------------------- azioni
    def _open_selected(self) -> None:
        for item in self._selected_items()[:5]:
            url = item.archived_url if (self.prefer_archive.isChecked()
                                        and item.archived_url) else item.url
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def _download_selected(self) -> None:
        chosen = self._selected_items() or self._items
        if not chosen:
            return
        prefer = self.prefer_archive.isChecked()
        urls = [(item.archived_url if (prefer and item.archived_url) else item.url)
                for item in chosen]
        if not confirm(self, "Scaricare i documenti",
                       "Scarico %d file in:\n%s\n\n%s"
                       % (len(urls), self.config.download_path(),
                          "Dalla copia archiviata dove disponibile."
                          if prefer else "Dalla versione online.")):
            return
        self.progress.setVisible(True)
        self.progress.setRange(0, len(urls))
        self.stop_button.setVisible(True)
        self._download_worker = DownloadWorker(urls, self.config)
        self._download_worker.progress.connect(
            lambda i, t, u: (self.progress.setValue(i),
                             self.status.emit("%d/%d %s" % (i, t, u[:80]))))
        self._download_worker.finished_all.connect(self._on_download_done)
        self._download_worker.failed.connect(
            lambda e: (self.progress.setVisible(False), message(self, "Errore", e, "error")))
        self._download_worker.start()

    def _on_download_done(self, outcomes, metadata) -> None:
        self.progress.setVisible(False)
        self.stop_button.setVisible(False)
        ok = sum(1 for o in outcomes if o.ok)
        message(self, "Download completato",
                "Scaricati %d file su %d in:\n%s"
                % (ok, len(outcomes), self.config.download_path()),
                "info" if ok else "warn")
        self.status.emit("Download: %d/%d" % (ok, len(outcomes)))

    def _send_selected(self) -> None:
        chosen = self._selected_items() or self._items
        if not chosen:
            return
        response = discovery.DiscoveryResponse(target=self.domain_edit.text(), urls=chosen)
        results = discovery.to_search_results(response, self.prefer_archive.isChecked())
        self.send_to_results.emit(results)
        self.status.emit("Inviati %d URL alla scheda Risultati" % len(results))

    def _export(self) -> None:
        if not self._items:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Esporta gli URL scoperti",
            str(Path.home() / "dorklab-scoperta.csv"),
            "CSV (*.csv);;JSON (*.json)")
        if not path:
            return
        response = discovery.DiscoveryResponse(target=self.domain_edit.text(), urls=self._items)
        results = discovery.to_search_results(response, self.prefer_archive.isChecked())
        try:
            if path.lower().endswith(".json"):
                exporters.results_to_json(results, path, self.domain_edit.text())
            else:
                exporters.results_to_csv(results, path)
        except OSError as exc:
            message(self, "Esportazione non riuscita", str(exc), "error")
            return
        self.status.emit("Esportato in %s" % path)

    def _stop(self) -> None:
        for worker in (self._worker, self._download_worker):
            if worker and hasattr(worker, "stop"):
                worker.stop()
        self.status.emit("Interruzione richiesta\u2026")

    def _set_actions_enabled(self, enabled: bool) -> None:
        for widget in (self.download_button, self.send_button, self.export_button):
            widget.setEnabled(enabled)

    def set_domain(self, domain: str) -> None:
        self.domain_edit.setText(audit.normalize_domain(domain))


def _fmt_ts(timestamp: str) -> str:
    if not timestamp or len(timestamp) < 8:
        return timestamp or "-"
    return "%s-%s-%s" % (timestamp[0:4], timestamp[4:6], timestamp[6:8])
