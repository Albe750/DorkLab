"""Finestra delle impostazioni: motori, credenziali, download, aspetto."""

from __future__ import annotations

from pathlib import Path

from .. import providers
from ..config import ENV_KEYS
from ..qtcompat import Qt, QtCore, QtWidgets
from .widgets import Badge, info_label, message


class SettingsDialog(QtWidgets.QDialog):
    """Configurazione persistente dell'applicazione."""

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._fields: dict[str, QtWidgets.QLineEdit] = {}

        self.setWindowTitle("Impostazioni — DorkLab")
        self.setMinimumSize(720, 560)

        layout = QtWidgets.QVBoxLayout(self)
        tabs = QtWidgets.QTabWidget(self)
        tabs.addTab(self._build_engines(), "Motori e credenziali")
        tabs.addTab(self._build_search(), "Ricerca")
        tabs.addTab(self._build_downloads(), "Download")
        tabs.addTab(self._build_appearance(), "Aspetto")
        layout.addWidget(tabs)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ motori
    def _build_engines(self) -> QtWidgets.QWidget:
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        inner = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(inner)
        layout.setSpacing(12)

        layout.addWidget(info_label(
            "Le chiavi sono salvate in ~/.config/dorklab/config.json con permessi "
            "600. In alternativa puoi esportarle come variabili d'ambiente: in quel "
            "caso hanno la precedenza e non vengono scritte su disco."))

        for kind in providers.kinds():
            items = [p for p in providers.by_kind(kind) if p.credentials]
            if not items:
                continue
            box = QtWidgets.QGroupBox("Motori: %s" % providers.KIND_LABELS[kind])
            box_layout = QtWidgets.QVBoxLayout(box)

            for provider in items:
                row_widget = QtWidgets.QWidget()
                form = QtWidgets.QFormLayout(row_widget)
                form.setContentsMargins(0, 4, 0, 10)

                header = QtWidgets.QHBoxLayout()
                name = QtWidgets.QLabel("<b>%s</b>" % provider.label)
                header.addWidget(name)
                state = Badge("pronto" if provider.available(self.config) else "da configurare",
                              "#16a34a" if provider.available(self.config) else "#c0392b")
                header.addWidget(state)
                header.addStretch(1)
                form.addRow(header)
                form.addRow(info_label(provider.description))

                for credential in provider.credentials:
                    edit = QtWidgets.QLineEdit(
                        self.config.get("credentials", {}).get(credential.key, ""))
                    if credential.secret:
                        edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
                    hint = credential.help
                    env_var = ENV_KEYS.get(credential.key)
                    if env_var:
                        hint += "  ·  variabile: %s" % env_var
                    edit.setPlaceholderText(hint)
                    edit.setToolTip("Origine attuale: %s"
                                    % self.config.credential_source(credential.key))
                    self._fields[credential.key] = edit
                    form.addRow(credential.label, edit)

                box_layout.addWidget(row_widget)
            layout.addWidget(box)

        # SearXNG accetta un URL invece di una chiave
        searx_box = QtWidgets.QGroupBox("SearXNG")
        searx_layout = QtWidgets.QFormLayout(searx_box)
        self.searx_edit = QtWidgets.QLineEdit(self.config.get("searxng_url") or "")
        self.searx_edit.setPlaceholderText("http://localhost:8888")
        searx_layout.addRow("URL istanza", self.searx_edit)
        searx_layout.addRow(info_label(
            "Abilita il formato JSON nel settings.yml dell'istanza "
            "(search.formats: [html, json])."))
        layout.addWidget(searx_box)

        layout.addStretch(1)
        scroll.setWidget(inner)
        return scroll

    # ----------------------------------------------------------------- ricerca
    def _build_search(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        self.max_results = QtWidgets.QSpinBox()
        self.max_results.setRange(5, 200)
        self.max_results.setSingleStep(5)
        self.max_results.setValue(int(self.config.get("max_results") or 60))
        layout.addRow("Risultati per ricerca", self.max_results)

        self.tavily_deep = QtWidgets.QCheckBox(
            "Scomponi le query in varianti per superare il tetto per chiamata")
        self.tavily_deep.setChecked(bool(self.config.get("tavily_deep", True)))
        self.tavily_deep.setToolTip(
            "Con Tavily ogni chiamata restituisce al massimo 20 risultati: "
            "scomponendo la query per estensione o dominio se ne ottengono di piu'.")
        layout.addRow("Profondita'", self.tavily_deep)
        layout.addRow(info_label(
            "Tavily viene sempre interrogato in modalita' advanced, con il massimo "
            "di frammenti per fonte e il contenuto grezzo incluso: non c'e' una "
            "modalita' ridotta da selezionare."))

        self.agentic_translate = QtWidgets.QCheckBox(
            "Traduci gli operatori in vincoli in linguaggio naturale")
        self.agentic_translate.setChecked(bool(self.config.get("agentic_translate", True)))
        self.agentic_translate.setToolTip(
            "I motori agentici non eseguono site:/filetype: alla lettera: "
            "esplicitare i vincoli migliora molto la pertinenza.")
        layout.addRow("Motori agentici", self.agentic_translate)

        self.claude_model = QtWidgets.QLineEdit(self.config.get("claude_model") or "")
        self.claude_model.setPlaceholderText("claude-opus-5")
        layout.addRow("Modello Claude", self.claude_model)

        self.perplexity_model = QtWidgets.QLineEdit(
            self.config.get("perplexity_model") or "")
        self.perplexity_model.setPlaceholderText("sonar-pro")
        layout.addRow("Modello Perplexity", self.perplexity_model)

        return widget

    # ---------------------------------------------------------------- download
    def _build_downloads(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        row = QtWidgets.QHBoxLayout()
        self.download_dir = QtWidgets.QLineEdit(self.config.download_path())
        browse = QtWidgets.QPushButton("Sfoglia…")
        browse.clicked.connect(self._pick_directory)
        row.addWidget(self.download_dir, 1)
        row.addWidget(browse)
        layout.addRow("Cartella dei download", row)

        self.delay = QtWidgets.QDoubleSpinBox()
        self.delay.setRange(0.0, 30.0)
        self.delay.setSingleStep(0.5)
        self.delay.setSuffix(" s")
        self.delay.setValue(self.config.number("request_delay", 1.5))
        layout.addRow("Ritardo fra le richieste", self.delay)

        self.max_mb = QtWidgets.QSpinBox()
        self.max_mb.setRange(1, 2000)
        self.max_mb.setSuffix(" MB")
        self.max_mb.setValue(int(self.config.get("max_download_mb") or 50))
        layout.addRow("Dimensione massima per file", self.max_mb)

        self.respect_robots = QtWidgets.QCheckBox("Rispetta robots.txt")
        self.respect_robots.setChecked(bool(self.config.get("respect_robots", True)))
        layout.addRow("", self.respect_robots)

        self.user_agent = QtWidgets.QLineEdit(self.config.get("user_agent") or "")
        layout.addRow("User-Agent", self.user_agent)
        layout.addRow(info_label(
            "Un User-Agent identificabile e un ritardo adeguato sono il modo "
            "corretto di scaricare documenti pubblici senza pesare sui server "
            "altrui ne' farsi bloccare."))
        return widget

    def _pick_directory(self) -> None:
        chosen = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Cartella dei download", self.download_dir.text() or str(Path.home()))
        if chosen:
            self.download_dir.setText(chosen)

    # ----------------------------------------------------------------- aspetto
    def _build_appearance(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        self.theme = QtWidgets.QComboBox()
        for value, label in (("auto", "Automatico (segue il sistema)"),
                             ("light", "Chiaro"), ("dark", "Scuro")):
            self.theme.addItem(label, value)
        index = self.theme.findData(self.config.get("theme") or "auto")
        self.theme.setCurrentIndex(max(0, index))
        layout.addRow("Tema", self.theme)
        layout.addRow(info_label(
            "Il cambio di tema viene applicato subito dopo il salvataggio."))
        return widget

    # ------------------------------------------------------------- salvataggio
    def accept(self) -> None:  # noqa: D102 - firma Qt
        for key, edit in self._fields.items():
            self.config.set_credential(key, edit.text())
        self.config.set("searxng_url", self.searx_edit.text().strip())
        self.config.set("max_results", self.max_results.value())
        self.config.set("tavily_deep", self.tavily_deep.isChecked())
        self.config.set("agentic_translate", self.agentic_translate.isChecked())
        self.config.set("claude_model", self.claude_model.text().strip() or "claude-opus-5")
        self.config.set("perplexity_model",
                        self.perplexity_model.text().strip() or "sonar-pro")
        self.config.set("download_dir", self.download_dir.text().strip())
        self.config.set("request_delay", self.delay.value())
        self.config.set("max_download_mb", self.max_mb.value())
        self.config.set("respect_robots", self.respect_robots.isChecked())
        self.config.set("user_agent", self.user_agent.text().strip())
        self.config.set("theme", self.theme.currentData())
        try:
            self.config.save()
        except OSError as exc:
            message(self, "Salvataggio non riuscito", str(exc), "error")
            return
        super().accept()
