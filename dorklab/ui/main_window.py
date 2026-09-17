"""Finestra principale: collega le schede, i motori e la cronologia."""

from __future__ import annotations

from .. import APP_NAME, __version__, providers
from ..config import Config
from ..paths import ensure_dirs
from ..qtcompat import Qt, QtCore, QtGui, QtWidgets
from ..store import Store
from . import style
from .dialog_settings import SettingsDialog
from .tab_audit import AuditTab
from .tab_builder import BuilderTab
from .tab_discovery import DiscoveryTab
from .tab_ghdb import GhdbTab
from .tab_history import HistoryTab
from .tab_results import ResultsTab
from .widgets import confirm, message
from .workers import SearchWorker

FIRST_RUN_KEY = "accepted_terms"

TERMS = """<h3>Uso consapevole</h3>
<p><b>DorkLab</b> compone interrogazioni per i motori di ricerca. Non attacca
sistemi, non sfrutta vulnerabilita' e non accede a nulla che non sia gia'
pubblicamente indicizzato.</p>
<ul>
<li>La ricerca documentale e l'OSINT su fonti pubbliche sono attivita' lecite.</li>
<li>La scheda <b>Audit difensivo</b> serve a verificare la <i>tua</i>
esposizione: richiede di dichiarare il dominio e di confermare di esserne
proprietario o di avere un'autorizzazione scritta.</li>
<li>Trovare un documento non autorizza a usarne il contenuto: restano validi
diritto d'autore, segreto industriale e normativa sui dati personali.</li>
<li>Se durante una verifica emergono dati personali altrui, la strada corretta
e' la segnalazione responsabile, non la raccolta.</li>
</ul>
<p>Procedendo dichiari di usare lo strumento nel rispetto della legge e delle
autorizzazioni di cui disponi.</p>
"""


class MainWindow(QtWidgets.QMainWindow):
    """Contenitore principale dell'applicazione."""

    def __init__(self) -> None:
        super().__init__()
        ensure_dirs()
        self.config = Config.load()
        self.store = Store()
        self._worker: SearchWorker | None = None

        self.setWindowTitle("%s %s" % (APP_NAME, __version__))
        self.resize(1280, 860)
        self.setMinimumSize(1020, 700)

        self._build_tabs()
        self._build_toolbar()
        self._build_status()
        self.apply_theme()
        self._restore_geometry()
        QtCore.QTimer.singleShot(200, self._maybe_show_terms)

    # ------------------------------------------------------------- costruzione
    def _build_tabs(self) -> None:
        self.tabs = QtWidgets.QTabWidget(self)
        self.tabs.setDocumentMode(True)

        self.builder = BuilderTab(self.config, self)
        self.results = ResultsTab(self.config, self)
        self.discovery = DiscoveryTab(self.config, self)
        self.ghdb = GhdbTab(self.config, self)
        self.audit = AuditTab(self.config, self)
        self.history = HistoryTab(self.store, self)

        self.tabs.addTab(self.builder, "Costruttore")
        self.tabs.addTab(self.results, "Risultati")
        self.tabs.addTab(self.discovery, "Scoperta")
        self.tabs.addTab(self.ghdb, "GHDB")
        self.tabs.addTab(self.audit, "Audit difensivo")
        self.tabs.addTab(self.history, "Cronologia")
        self.setCentralWidget(self.tabs)

        self.builder.search_requested.connect(self.run_search)
        self.builder.open_requested.connect(self.open_in_browser)
        self.builder.save_requested.connect(self.save_dork)
        self.results.status.connect(self.set_status)
        self.discovery.status.connect(self.set_status)
        self.discovery.send_to_results.connect(self._discovery_to_results)
        self.discovery.load_in_builder.connect(self.load_query)
        self.ghdb.load_in_builder.connect(self.load_query)
        self.ghdb.use_for_audit.connect(self._ghdb_to_audit)
        self.ghdb.status.connect(self.set_status)
        self.audit.status.connect(self.set_status)
        self.audit.results_ready.connect(self._audit_results)
        self.history.load_query.connect(self.load_query)
        self.history.status.connect(self.set_status)

    def _build_toolbar(self) -> None:
        toolbar = QtWidgets.QToolBar("Principale", self)
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        settings_action = QtGui.QAction("Impostazioni", self)
        settings_action.setShortcut(QtGui.QKeySequence("Ctrl+,"))
        settings_action.triggered.connect(self.open_settings)
        toolbar.addAction(settings_action)

        toolbar.addSeparator()
        search_action = QtGui.QAction("Cerca", self)
        search_action.setShortcut(QtGui.QKeySequence("Ctrl+Return"))
        search_action.triggered.connect(self.builder.trigger_search)
        toolbar.addAction(search_action)

        browser_action = QtGui.QAction("Apri nel browser", self)
        browser_action.setShortcut(QtGui.QKeySequence("Ctrl+B"))
        browser_action.triggered.connect(self.builder.trigger_open)
        toolbar.addAction(browser_action)

        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                             QtWidgets.QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        about_action = QtGui.QAction("Informazioni", self)
        about_action.triggered.connect(self.show_about)
        toolbar.addAction(about_action)

    def _build_status(self) -> None:
        self.status_bar = QtWidgets.QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.busy = QtWidgets.QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setMaximumWidth(140)
        self.busy.setVisible(False)
        self.status_bar.addPermanentWidget(self.busy)
        self.set_status("Pronto")

    # ---------------------------------------------------------------- ricerca
    def run_search(self, provider_id: str, query: str, limit: int) -> None:
        provider = providers.get(provider_id)
        if provider is None:
            return
        if provider.kind == "browser":
            # I motori browser non riportano i risultati nell'app: lo si dice in
            # modo esplicito invece di aprire il browser di sorpresa.
            if confirm(self, "Motore che apre il browser",
                       "\u00ab%s\u00bb apre i risultati nel browser e non li "
                       "riporta nella scheda Risultati.\n\nPer avere i risultati "
                       "dentro l'app scegli un motore API o agentico, per esempio "
                       "Tavily.\n\nApro comunque nel browser?" % provider.label):
                self.open_in_browser(provider_id, query)
            return
        if not provider.available(self.config):
            missing = ", ".join(c.label for c in provider.missing_credentials(self.config))
            if confirm(self, "Credenziali mancanti",
                       "Il motore %s richiede: %s\n\nApro le impostazioni?"
                       % (provider.label, missing)):
                self.open_settings()
            return
        if self._worker is not None:
            message(self, "Ricerca in corso",
                    "Attendi la fine della ricerca in corso.", "warn")
            return

        self.busy.setVisible(True)
        self.set_status("Ricerca su %s…" % provider.label)
        self._worker = SearchWorker(provider_id, query, self.config, limit, self)
        self._worker.progress.connect(self.set_status)
        self._worker.finished_ok.connect(self._search_done)
        self._worker.failed.connect(self._search_failed)
        self._worker.finished.connect(self._search_cleanup)
        self._worker.start()

    def _search_done(self, response) -> None:
        self.results.set_response(response)
        self.tabs.setCurrentWidget(self.results)
        self.store.log_run(response.query, response.provider, len(response.results))
        self.history.reload()
        self.set_status("%d risultati da %s" % (len(response.results), response.provider))
        if not response.results and not response.answer:
            message(self, "Nessun risultato",
                    "La query non ha prodotto risultati.\n\n"
                    "Suggerimenti: allarga i vincoli, rimuovi un operatore "
                    "oppure prova un motore diverso — gli indici non "
                    "coincidono fra i motori.", "info")

    def _search_failed(self, error: str) -> None:
        self.store.log_run(self.builder.query_text(),
                           self.config.get("provider") or "", 0, error=error)
        self.history.reload()
        self.set_status("Ricerca non riuscita")
        message(self, "Ricerca non riuscita", error, "error")

    def _search_cleanup(self) -> None:
        self.busy.setVisible(False)
        self._worker = None

    def open_in_browser(self, provider_id: str, query: str) -> None:
        provider = providers.get(provider_id)
        if provider is None:
            return
        url = provider.build_url(query)
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))
        self.store.log_run(query, provider_id, 0, context="browser")
        self.history.reload()
        self.set_status("Aperto nel browser: %s" % provider.label)

    # ------------------------------------------------------------------ varie
    def load_query(self, query: str) -> None:
        self.builder.set_query_text(query)
        self.tabs.setCurrentWidget(self.builder)

    def save_dork(self, query: str) -> None:
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Salva il dork", "Nome:", text=query[:40])
        if not ok or not name.strip():
            return
        self.store.save_dork(name.strip(), query,
                             self.builder.query.to_dict())
        self.history.reload()
        self.set_status("Dork salvato: %s" % name.strip())

    def _ghdb_to_audit(self, dork: str) -> None:
        self.tabs.setCurrentWidget(self.audit)
        self.audit.add_custom_query(dork)

    def _discovery_to_results(self, results) -> None:
        self.results.append_results(results)
        self.tabs.setCurrentWidget(self.results)
        self.set_status("%d URL scoperti aggiunti ai Risultati" % len(results))

    def _audit_results(self, response) -> None:
        self.results.append_results(response.results)
        self.store.log_run(response.query, response.provider,
                           len(response.results), context="audit")

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            self.apply_theme()
            self.builder.refresh_providers()
            self.set_status("Impostazioni salvate")

    def apply_theme(self) -> None:
        application = QtWidgets.QApplication.instance()
        if application is None:
            return
        palette = application.palette()
        dark_hint = palette.color(QtGui.QPalette.ColorRole.Window).lightness() < 128
        application.setStyleSheet(
            style.stylesheet(self.config.get("theme") or "auto", dark_hint))

    def set_status(self, text: str) -> None:
        self.status_bar.showMessage(text, 15000)

    def show_about(self) -> None:
        provider_count = len(providers.all_providers())
        QtWidgets.QMessageBox.about(
            self, "Informazioni su %s" % APP_NAME,
            "<h3>%s %s</h3>"
            "<p>Ricerca avanzata, estrazione documentale e protective dorking.</p>"
            "<p><b>%d motori</b> configurabili: browser, API e agentici.<br>"
            "Binding Qt in uso: %s</p>"
            "<p style='color:#6b7280'>Usa lo strumento nel rispetto della legge "
            "e solo su sistemi per cui hai autorizzazione.</p>"
            % (APP_NAME, __version__, provider_count, _qt_api()))

    def _maybe_show_terms(self) -> None:
        if self.config.get(FIRST_RUN_KEY):
            return
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle("%s — primo avvio" % APP_NAME)
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(TERMS)
        box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok
                               | QtWidgets.QMessageBox.StandardButton.Cancel)
        box.button(QtWidgets.QMessageBox.StandardButton.Ok).setText("Ho capito")
        box.button(QtWidgets.QMessageBox.StandardButton.Cancel).setText("Esci")
        if box.exec() != QtWidgets.QMessageBox.StandardButton.Ok:
            self.close()
            return
        self.config.set(FIRST_RUN_KEY, True)
        try:
            self.config.save()
        except OSError:
            pass

    # ------------------------------------------------------------- geometria
    def _restore_geometry(self) -> None:
        window = self.config.get("window") or {}
        if window.get("width") and window.get("height"):
            self.resize(int(window["width"]), int(window["height"]))

    def closeEvent(self, event) -> None:  # noqa: N802 - firma Qt
        self.config.set("window", {"width": self.width(), "height": self.height()})
        try:
            self.config.save()
        except OSError:
            pass
        if self._worker and self._worker.isRunning():
            self._worker.quit()
            self._worker.wait(2000)
        self.store.close()
        super().closeEvent(event)


def _qt_api() -> str:
    from ..qtcompat import QT_API

    return QT_API
