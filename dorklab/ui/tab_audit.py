"""Scheda "Audit difensivo": protective dorking sul proprio dominio.

Ogni query generata qui e' vincolata al dominio dichiarato e la generazione e'
subordinata a una conferma esplicita di autorizzazione. E' una scelta di
progetto, non un dettaglio dell'interfaccia: lo stesso strumento che aiuta a
mettere in sicurezza il proprio perimetro non deve rendere comodo curiosare in
quello altrui.
"""

from __future__ import annotations

from pathlib import Path

from .. import audit, catalog, exporters, providers
from ..qtcompat import Qt, QtCore, QtGui, QtWidgets, Signal
from .widgets import Badge, BubbleBar, confirm, info_label, message
from .workers import BatchSearchWorker


class AuditTab(QtWidgets.QWidget):
    """Genera ed esegue un piano di verifica dell'esposizione."""

    status = Signal(str)
    results_ready = Signal(object)

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.plan: audit.AuditPlan | None = None
        self._worker: BatchSearchWorker | None = None
        self._check_bubbles: dict = {}
        self._browser_queue: list[str] = []

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        layout.addWidget(self._build_scope())
        layout.addWidget(self._build_checks())

        splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._build_table())
        splitter.addWidget(self._build_detail())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        layout.addLayout(self._build_actions())
        self.progress = QtWidgets.QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self._update_state()

    # ------------------------------------------------------------- perimetro
    def _build_scope(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Perimetro autorizzato")
        layout = QtWidgets.QVBoxLayout(box)

        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Dominio"))
        self.domain_edit = QtWidgets.QLineEdit()
        self.domain_edit.setPlaceholderText("esempio.it")
        self.domain_edit.textChanged.connect(self._update_state)
        row.addWidget(self.domain_edit, 1)
        self.domain_badge = Badge("nessun dominio", "#6b7280")
        row.addWidget(self.domain_badge)
        layout.addLayout(row)

        self.authorized = QtWidgets.QCheckBox(
            "Dichiaro di essere proprietario di questo dominio oppure di avere "
            "un'autorizzazione scritta a verificarlo.")
        self.authorized.toggled.connect(self._update_state)
        layout.addWidget(self.authorized)

        layout.addWidget(info_label(
            "Le query di questa scheda vengono sempre eseguite con il vincolo "
            "site: sul dominio indicato. Interrogare un motore di ricerca non "
            "tocca i tuoi sistemi, ma la verifica dei risultati e le azioni "
            "conseguenti vanno svolte solo su cio' che ti appartiene."))
        return box

    def _build_checks(self) -> QtWidgets.QWidget:
        box = QtWidgets.QGroupBox("Controlli da eseguire")
        layout = QtWidgets.QVBoxLayout(box)

        self.check_bar = BubbleBar()
        colors = catalog.severities()
        for check in catalog.audit_checks():
            color = colors.get(check["severity"], {}).get("color", "#6b7280")
            tooltip = "%s\n\n%s\n\nQuery: %d" % (
                check["desc"], check["why"], len(check["queries"]))
            bubble = self.check_bar.add(
                "%s  ·  %s" % (check["label"],
                                    colors.get(check["severity"], {}).get("label", "")),
                check["id"], tooltip=tooltip, checkable=True,
                sensitive=check["severity"] in {"critica", "alta"})
            self._check_bubbles[check["id"]] = bubble
        layout.addWidget(self.check_bar)

        row = QtWidgets.QHBoxLayout()
        select_all = QtWidgets.QPushButton("Seleziona tutto")
        select_all.clicked.connect(lambda: self._set_all(True))
        select_none = QtWidgets.QPushButton("Deseleziona")
        select_none.clicked.connect(lambda: self._set_all(False))
        select_critical = QtWidgets.QPushButton("Solo critici e alti")
        select_critical.clicked.connect(self._select_critical)
        self.generate_button = QtWidgets.QPushButton("Genera piano")
        self.generate_button.setObjectName("primary")
        self.generate_button.clicked.connect(self.generate_plan)
        row.addWidget(select_all)
        row.addWidget(select_none)
        row.addWidget(select_critical)
        row.addStretch(1)
        row.addWidget(self.generate_button)
        layout.addLayout(row)
        return box

    def _build_table(self) -> QtWidgets.QWidget:
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Gravita'", "Controllo", "Query", "Stato", "Risultati"])
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
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._show_detail)
        self.table.itemDoubleClicked.connect(lambda *_: self.open_current_in_browser())
        return self.table

    def _build_detail(self) -> QtWidgets.QWidget:
        self.detail = QtWidgets.QTextBrowser()
        self.detail.setOpenExternalLinks(True)
        self.detail.setHtml(
            "<p style='color:#6b7280'>Genera un piano e seleziona un controllo "
            "per vedere perche' conta e come rimediare.</p>")
        return self.detail

    def _build_actions(self) -> QtWidgets.QHBoxLayout:
        row = QtWidgets.QHBoxLayout()
        self.run_button = QtWidgets.QPushButton("Esegui il piano")
        self.run_button.setObjectName("primary")
        self.run_button.clicked.connect(self.run_plan)
        self.browser_button = QtWidgets.QPushButton("Apri nel browser")
        self.browser_button.setToolTip(
            "Apre la query selezionata nel motore predefinito del browser.")
        self.browser_button.clicked.connect(self.open_current_in_browser)
        self.report_button = QtWidgets.QPushButton("Genera report…")
        self.report_button.clicked.connect(self.export_report)
        self.copy_button = QtWidgets.QPushButton("Copia tutte le query")
        self.copy_button.clicked.connect(self.copy_queries)
        self.stop_button = QtWidgets.QPushButton("Interrompi")
        self.stop_button.setObjectName("danger")
        self.stop_button.clicked.connect(self._stop)
        self.stop_button.setVisible(False)

        for widget in (self.run_button, self.browser_button, self.report_button,
                       self.copy_button):
            row.addWidget(widget)
        row.addStretch(1)
        self.summary_badge = Badge("nessun piano", "#6b7280")
        row.addWidget(self.summary_badge)
        row.addWidget(self.stop_button)
        return row

    # --------------------------------------------------------------- stato
    def _set_all(self, value: bool) -> None:
        for bubble in self._check_bubbles.values():
            bubble.setChecked(value)

    def _select_critical(self) -> None:
        for check in catalog.audit_checks():
            self._check_bubbles[check["id"]].setChecked(
                check["severity"] in {"critica", "alta"})

    def _update_state(self) -> None:
        domain = self.domain_edit.text()
        valid = audit.is_valid_domain(domain)
        normalized = audit.normalize_domain(domain)

        if not domain.strip():
            self.domain_badge.setText("nessun dominio")
            self.domain_badge.set_color("#6b7280")
        elif valid:
            self.domain_badge.setText(normalized)
            self.domain_badge.set_color("#16a34a")
        else:
            self.domain_badge.setText("non valido")
            self.domain_badge.set_color("#c0392b")

        ready = valid and self.authorized.isChecked()
        self.generate_button.setEnabled(ready)
        self.generate_button.setToolTip(
            "" if ready else "Inserisci un dominio valido e conferma l'autorizzazione.")

        has_plan = bool(self.plan and self.plan.queries)
        for widget in (self.run_button, self.report_button, self.copy_button,
                       self.browser_button):
            widget.setEnabled(has_plan)

    # ---------------------------------------------------------------- piano
    def generate_plan(self) -> None:
        chosen = [check_id for check_id, bubble in self._check_bubbles.items()
                  if bubble.isChecked()]
        if not chosen:
            message(self, "Nessun controllo selezionato",
                    "Seleziona almeno un controllo da eseguire.", "warn")
            return
        try:
            self.plan = audit.build_plan(
                self.domain_edit.text(), chosen,
                authorized=self.authorized.isChecked())
        except audit.AuthorizationError as exc:
            message(self, "Verifica non consentita", str(exc), "warn")
            return

        self._populate()
        self.status.emit("Piano generato: %d query su %s"
                         % (len(self.plan.queries), self.plan.domain))
        self._update_state()

    def add_custom_query(self, dork: str) -> None:
        """Aggiunge al piano una voce arrivata dalla scheda GHDB."""
        if not audit.is_valid_domain(self.domain_edit.text()):
            message(self, "Dominio mancante",
                    "Inserisci il dominio autorizzato prima di aggiungere una verifica.",
                    "warn")
            return
        if not self.authorized.isChecked():
            message(self, "Autorizzazione mancante",
                    "Conferma di essere autorizzato a verificare questo dominio.", "warn")
            return

        scoped = audit.scoped_ghdb_query(dork, self.domain_edit.text(),
                                         authorized=self.authorized.isChecked())
        if self.plan is None:
            self.plan = audit.AuditPlan(domain=audit.normalize_domain(self.domain_edit.text()))
        self.plan.queries.append(audit.AuditQuery(
            check_id="ghdb", check_label="Voce dal catalogo GHDB", severity="media",
            query=scoped, description="Verifica importata dal catalogo GHDB.",
            why="Voce selezionata manualmente dal catalogo.",
            remediation=["Valuta il risultato nel contesto del tuo sito."]))
        self._populate()
        self._update_state()
        self.status.emit("Verifica aggiunta al piano: %s" % scoped[:70])

    def _populate(self) -> None:
        self.table.setRowCount(0)
        if not self.plan:
            return
        colors = catalog.severities()
        for item in self.plan.by_severity():
            row = self.table.rowCount()
            self.table.insertRow(row)

            severity = QtWidgets.QTableWidgetItem(
                colors.get(item.severity, {}).get("label", item.severity))
            severity.setForeground(QtGui.QBrush(QtGui.QColor(
                colors.get(item.severity, {}).get("color", "#6b7280"))))
            self.table.setItem(row, 0, severity)
            self.table.setItem(row, 1, QtWidgets.QTableWidgetItem(item.check_label))
            query_item = QtWidgets.QTableWidgetItem(item.query)
            query_item.setToolTip(item.query)
            self.table.setItem(row, 2, query_item)
            self.table.setItem(row, 3, QtWidgets.QTableWidgetItem(item.status))
            hits = QtWidgets.QTableWidgetItem()
            hits.setData(Qt.ItemDataRole.DisplayRole, item.hits)
            if item.hits:
                hits.setForeground(QtGui.QBrush(QtGui.QColor("#c0392b")))
            self.table.setItem(row, 4, hits)

        summary = self.plan.summary()
        self.summary_badge.setText(
            "%d query · %d eseguite · %d da verificare"
            % (summary["totali"], summary["eseguite"], summary["con_risultati"]))
        self.summary_badge.set_color("#c0392b" if summary["con_risultati"] else "#16a34a")

    def current_query(self) -> audit.AuditQuery | None:
        if not self.plan:
            return None
        rows = {index.row() for index in self.table.selectedIndexes()}
        if not rows:
            return None
        ordered = self.plan.by_severity()
        row = sorted(rows)[0]
        return ordered[row] if row < len(ordered) else None

    def _show_detail(self) -> None:
        item = self.current_query()
        if item is None:
            return
        steps = "".join("<li>%s</li>" % _esc(step) for step in item.remediation)
        colors = catalog.severities()
        color = colors.get(item.severity, {}).get("color", "#6b7280")
        self.detail.setHtml(
            "<h3>%s</h3>"
            "<p><span style='color:%s;font-weight:600'>%s</span> &middot; stato: %s</p>"
            "<pre style='white-space:pre-wrap'>%s</pre>"
            "<p>%s</p><p><b>Perche' conta</b><br>%s</p>"
            "<p><b>Come rimediare</b></p><ul>%s</ul>%s"
            % (_esc(item.check_label), color,
               _esc(colors.get(item.severity, {}).get("label", item.severity)),
               _esc(item.status), _esc(item.query), _esc(item.description),
               _esc(item.why), steps,
               ("<p style='color:#c0392b'>Errore: %s</p>" % _esc(item.error))
               if item.error else "")
        )

    # ------------------------------------------------------------- esecuzione
    def run_plan(self) -> None:
        if not self.plan or not self.plan.queries:
            return
        provider = providers.get(self.config.get("provider") or "")
        if provider is None:
            message(self, "Motore non configurato",
                    "Scegli un motore nella scheda Costruttore.", "warn")
            return
        if provider.kind == "browser":
            self._run_in_browser()
            return
        if not provider.available(self.config):
            missing = ", ".join(c.label for c in provider.missing_credentials(self.config))
            message(self, "Credenziali mancanti",
                    "Il motore %s richiede: %s\nImpostazioni → Motori."
                    % (provider.label, missing), "warn")
            return

        count = len(self.plan.queries)
        if not confirm(self, "Eseguire il piano",
                       "Verranno eseguite %d ricerche su %s tramite %s.\n"
                       "Tutte le query sono vincolate al dominio %s.\n\nProcedo?"
                       % (count, self.plan.domain, provider.label, self.plan.domain)):
            return

        self.progress.setVisible(True)
        self.progress.setRange(0, count)
        self.progress.setValue(0)
        self.stop_button.setVisible(True)
        self.run_button.setEnabled(False)

        self._worker = BatchSearchWorker(
            provider.id, [q.query for q in self.plan.by_severity()],
            self.config, limit=10)
        self._worker.progress.connect(self._on_progress)
        self._worker.one_done.connect(self._on_one_done)
        self._worker.one_failed.connect(self._on_one_failed)
        self._worker.finished_all.connect(self._on_finished)
        self._worker.start()

    def _run_in_browser(self) -> None:
        if not self.plan:
            return
        queries = [q.query for q in self.plan.by_severity()]
        if not confirm(self, "Apertura nel browser",
                       "Il motore selezionato non ha un'API: le %d query verranno "
                       "aperte nel browser una alla volta.\n\nAprire la prima?"
                       % len(queries)):
            return
        self._browser_queue = queries
        self._open_next_in_queue()

    def _open_next_in_queue(self) -> None:
        if not self._browser_queue:
            self.status.emit("Coda del browser completata")
            return
        query = self._browser_queue.pop(0)
        provider = providers.get(self.config.get("provider") or "google_browser")
        url = provider.build_url(query) if provider else ""
        if url:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))
        remaining = len(self._browser_queue)
        self.status.emit("Aperta 1 query, ne restano %d" % remaining)
        if remaining and confirm(self, "Coda audit",
                                 "Restano %d query. Apro la prossima?" % remaining):
            self._open_next_in_queue()

    def open_current_in_browser(self) -> None:
        item = self.current_query()
        if item is None:
            return
        provider = providers.get(self.config.get("provider") or "google_browser")
        if provider is None:
            return
        url = provider.build_url(item.query)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def _on_progress(self, index: int, total: int, query: str) -> None:
        self.progress.setValue(index)
        self.status.emit("Audit %d/%d: %s" % (index, total, query[:80]))

    def _on_one_done(self, index: int, response) -> None:
        if not self.plan:
            return
        ordered = self.plan.by_severity()
        if index < len(ordered):
            ordered[index].executed = True
            ordered[index].hits = len(response.results)
            ordered[index].error = ""
        if response.results:
            self.results_ready.emit(response)
        self._populate()

    def _on_one_failed(self, index: int, error: str) -> None:
        if not self.plan:
            return
        ordered = self.plan.by_severity()
        if index < len(ordered):
            ordered[index].executed = True
            ordered[index].error = error
        self._populate()

    def _on_finished(self) -> None:
        self.progress.setVisible(False)
        self.stop_button.setVisible(False)
        self.run_button.setEnabled(True)
        self._worker = None
        if not self.plan:
            return
        summary = self.plan.summary()
        message(self, "Audit completato",
                "Controlli eseguiti: %d su %d\n"
                "Con risultati da verificare: %d\n"
                "Errori: %d\n\n"
                "Un risultato non e' automaticamente una vulnerabilita': "
                "va sempre verificato manualmente."
                % (summary["eseguite"], summary["totali"],
                   summary["con_risultati"], summary["errori"]))

    def _stop(self) -> None:
        if self._worker:
            self._worker.stop()
            self.status.emit("Interruzione richiesta…")

    # ---------------------------------------------------------------- report
    def export_report(self) -> None:
        if not self.plan:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Salva il report",
            str(Path.home() / ("esposizione-%s.md" % self.plan.domain)),
            "Markdown (*.md);;HTML (*.html);;CSV (*.csv)")
        if not path:
            return
        suffix = Path(path).suffix.lower()
        try:
            if suffix == ".html":
                exporters.audit_to_html(self.plan, path)
            elif suffix == ".csv":
                exporters.audit_to_csv(self.plan, path)
            else:
                exporters.audit_to_markdown(
                    self.plan, path,
                    {"motore": self.config.get("provider"),
                     "controlli": len(self.plan.queries)})
        except OSError as exc:
            message(self, "Salvataggio non riuscito", str(exc), "error")
            return
        self.status.emit("Report salvato in %s" % path)
        message(self, "Report generato", "Salvato in:\n%s" % path)

    def copy_queries(self) -> None:
        if not self.plan:
            return
        text = "\n".join(q.query for q in self.plan.by_severity())
        QtWidgets.QApplication.clipboard().setText(text)
        self.status.emit("Copiate %d query" % len(self.plan.queries))


def _esc(text: str) -> str:
    import html

    return html.escape(text or "")
