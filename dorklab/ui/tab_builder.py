"""Scheda "Costruttore": composizione della query tramite bolle."""

from __future__ import annotations

from .. import catalog, providers
from ..qtcompat import Qt, QtCore, QtGui, QtWidgets, Signal
from ..query import DorkQuery, Token, group_of
from .flowlayout import FlowLayout
from .widgets import Badge, BubbleBar, SectionBox, TokenChip, info_label, message


class BuilderTab(QtWidgets.QWidget):
    """Tavolozza di bolle a sinistra, tela della query a destra."""

    search_requested = Signal(str, str, int)   # provider_id, query, limite
    open_requested = Signal(str, str)          # provider_id, query
    save_requested = Signal(str)
    query_changed = Signal(str)

    def __init__(self, config, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.query = DorkQuery()
        self._chips: list[TokenChip] = []
        self._filetype_bubbles: dict = {}
        self._recipe_fields: dict[str, QtWidgets.QLineEdit] = {}
        self._raw_mode = False

        splitter = QtWidgets.QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(self._build_palette())
        splitter.addWidget(self._build_canvas())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([420, 660])

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self.refresh_providers()
        self._refresh()

    # ------------------------------------------------------------- tavolozza
    def _build_palette(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget(self)
        outer = QtWidgets.QVBoxLayout(container)
        outer.setContentsMargins(0, 0, 6, 0)

        scroll = QtWidgets.QScrollArea(container)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        inner = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(inner)
        layout.setContentsMargins(2, 2, 8, 2)
        layout.setSpacing(14)

        # --- parole chiave
        keywords = SectionBox("Parole chiave",
                              "Il testo libero della ricerca. Invio per aggiungerlo.")
        klayout = QtWidgets.QVBoxLayout(keywords.body)
        klayout.setContentsMargins(0, 0, 0, 0)
        row = QtWidgets.QHBoxLayout()
        self.keyword_edit = QtWidgets.QLineEdit()
        self.keyword_edit.setPlaceholderText("es. rapporto di prova taratura")
        self.keyword_edit.returnPressed.connect(self._add_keyword)
        add_button = QtWidgets.QPushButton("Aggiungi")
        add_button.clicked.connect(self._add_keyword)
        exact_button = QtWidgets.QPushButton("Frase esatta")
        exact_button.setToolTip("Aggiunge il testo tra virgolette")
        exact_button.clicked.connect(lambda: self._add_keyword(exact=True))
        row.addWidget(self.keyword_edit, 1)
        row.addWidget(add_button)
        row.addWidget(exact_button)
        klayout.addLayout(row)
        layout.addWidget(keywords)

        # --- operatori per categoria
        grouped = catalog.operators_by_category()
        for category in catalog.operator_categories():
            items = grouped.get(category["id"]) or []
            if not items:
                continue
            section = SectionBox(category["label"], category["desc"],
                                 expanded=category["id"] in {"scope", "content", "files"})
            body = QtWidgets.QVBoxLayout(section.body)
            body.setContentsMargins(0, 0, 0, 0)
            bar = BubbleBar()
            for item in items:
                tooltip = "%s\n\nEsempio: %s" % (item["desc"], item.get("example", ""))
                if item.get("deprecated"):
                    tooltip += "\n\nOperatore dismesso dal motore."
                bar.add(item["label"] + (" ⚠" if item.get("deprecated") else ""),
                        item, tooltip=tooltip)
            bar.clicked.connect(self._add_operator)
            body.addWidget(bar)
            setattr(self, "_bar_%s" % category["id"], bar)
            layout.addWidget(section)

        # --- gruppi di tipi di file
        files = SectionBox(
            "Tipi di documento",
            "Seleziona uno o piu' gruppi: diventano un blocco (filetype:a OR filetype:b).")
        flayout = QtWidgets.QVBoxLayout(files.body)
        flayout.setContentsMargins(0, 0, 0, 0)
        self.filetype_bar = BubbleBar()
        for group in catalog.filetype_groups():
            tooltip = "%s\n\n%s" % (group["desc"], ", ".join(group["extensions"]))
            bubble = self.filetype_bar.add(
                group["label"], group, tooltip=tooltip, checkable=True,
                sensitive=group.get("sensitive", False))
            self._filetype_bubbles[group["id"]] = bubble
        flayout.addWidget(self.filetype_bar)

        frow = QtWidgets.QHBoxLayout()
        apply_group = QtWidgets.QPushButton("Aggiungi selezionati")
        apply_group.clicked.connect(self._add_filetype_groups)
        clear_group = QtWidgets.QPushButton("Deseleziona")
        clear_group.clicked.connect(self._clear_filetype_groups)
        frow.addWidget(apply_group)
        frow.addWidget(clear_group)
        frow.addStretch(1)
        flayout.addLayout(frow)
        flayout.addWidget(info_label(
            "I gruppi con bordo arancione sono sensibili: usali soprattutto "
            "nell'audit del tuo dominio."))
        layout.addWidget(files)

        # --- ricette
        recipes = SectionBox("Ricette pronte",
                             "Schemi collaudati: scegline uno e completa i campi.",
                             expanded=False)
        rlayout = QtWidgets.QVBoxLayout(recipes.body)
        rlayout.setContentsMargins(0, 0, 0, 0)
        self.recipe_list = QtWidgets.QComboBox()
        self.recipe_list.addItem("— scegli una ricetta —", None)
        for recipe in catalog.recipes():
            self.recipe_list.addItem("%s  ·  %s" % (recipe["label"], recipe["category"]),
                                     recipe["id"])
        self.recipe_list.currentIndexChanged.connect(self._recipe_selected)
        rlayout.addWidget(self.recipe_list)

        self.recipe_desc = info_label("")
        rlayout.addWidget(self.recipe_desc)
        self.recipe_form = QtWidgets.QWidget()
        self.recipe_form_layout = QtWidgets.QFormLayout(self.recipe_form)
        self.recipe_form_layout.setContentsMargins(0, 4, 0, 4)
        rlayout.addWidget(self.recipe_form)
        self.recipe_apply = QtWidgets.QPushButton("Applica ricetta")
        self.recipe_apply.clicked.connect(self._apply_recipe)
        self.recipe_apply.setEnabled(False)
        rlayout.addWidget(self.recipe_apply)
        layout.addWidget(recipes)

        layout.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return container

    # ------------------------------------------------------------------ tela
    def _build_canvas(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget(self)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(6, 2, 2, 2)
        layout.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("Query")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        self.token_count = Badge("0 token", "#6b7280")
        header.addWidget(self.token_count)
        layout.addLayout(header)

        self.canvas = QtWidgets.QFrame()
        self.canvas.setObjectName("canvas")
        self.canvas.setMinimumHeight(110)
        self.canvas_layout = FlowLayout(self.canvas, margin=10, spacing=7)
        canvas_scroll = QtWidgets.QScrollArea()
        canvas_scroll.setWidgetResizable(True)
        canvas_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        canvas_scroll.setWidget(self.canvas)
        canvas_scroll.setMinimumHeight(130)
        canvas_scroll.setMaximumHeight(260)
        layout.addWidget(canvas_scroll)

        self.empty_hint = info_label(
            "Clicca le bolle a sinistra per comporre la query. "
            "Ogni bolla diventa un elemento modificabile: valore in linea, "
            "− per negarlo, & / OR per il legame logico.")
        layout.addWidget(self.empty_hint)

        preview_header = QtWidgets.QHBoxLayout()
        preview_title = QtWidgets.QLabel("Anteprima")
        preview_title.setObjectName("sectionTitle")
        preview_header.addWidget(preview_title)
        preview_header.addStretch(1)
        self.raw_toggle = QtWidgets.QPushButton("Modifica come testo")
        self.raw_toggle.setCheckable(True)
        self.raw_toggle.setToolTip(
            "Scrivi o incolla un dork: alla disattivazione torna in bolle.")
        self.raw_toggle.toggled.connect(self._toggle_raw)
        preview_header.addWidget(self.raw_toggle)
        copy_button = QtWidgets.QPushButton("Copia")
        copy_button.clicked.connect(self._copy)
        preview_header.addWidget(copy_button)
        layout.addLayout(preview_header)

        self.preview = QtWidgets.QPlainTextEdit()
        self.preview.setObjectName("preview")
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(74)
        self.preview.setMaximumHeight(120)
        layout.addWidget(self.preview)

        engine_box = QtWidgets.QGroupBox("Motore di ricerca")
        engine_layout = QtWidgets.QVBoxLayout(engine_box)

        row = QtWidgets.QHBoxLayout()
        self.provider_combo = QtWidgets.QComboBox()
        self.provider_combo.currentIndexChanged.connect(self._provider_changed)
        row.addWidget(self.provider_combo, 1)
        row.addWidget(QtWidgets.QLabel("Risultati"))
        self.limit_spin = QtWidgets.QSpinBox()
        self.limit_spin.setRange(5, 200)
        self.limit_spin.setSingleStep(5)
        self.limit_spin.setValue(int(self.config.get("max_results") or 60))
        self.limit_spin.setToolTip(
            "Oltre 20 risultati i motori agentici scompongono la query in varianti.")
        row.addWidget(self.limit_spin)
        engine_layout.addLayout(row)

        badges = QtWidgets.QHBoxLayout()
        badges.setSpacing(6)
        self.kind_badge = Badge("", "#3d7bff")
        self.dork_badge = Badge("", "#6b7280")
        self.status_badge = Badge("", "#16a34a")
        badges.addWidget(self.kind_badge)
        badges.addWidget(self.dork_badge)
        badges.addWidget(self.status_badge)
        badges.addStretch(1)
        engine_layout.addLayout(badges)

        self.provider_hint = info_label("")
        engine_layout.addWidget(self.provider_hint)
        layout.addWidget(engine_box)

        actions = QtWidgets.QHBoxLayout()
        self.search_button = QtWidgets.QPushButton("Cerca")
        self.search_button.setObjectName("primary")
        self.search_button.clicked.connect(self._emit_search)
        self.browser_button = QtWidgets.QPushButton("Apri nel browser")
        self.browser_button.clicked.connect(self._emit_open)
        save_button = QtWidgets.QPushButton("Salva dork")
        save_button.clicked.connect(self._emit_save)
        clear_button = QtWidgets.QPushButton("Pulisci")
        clear_button.setObjectName("danger")
        clear_button.clicked.connect(self.clear)
        actions.addWidget(self.search_button)
        actions.addWidget(self.browser_button)
        actions.addWidget(save_button)
        actions.addStretch(1)
        actions.addWidget(clear_button)
        layout.addLayout(actions)
        layout.addStretch(1)
        return container

    # ------------------------------------------------------------- operazioni
    def _add_keyword(self, exact: bool = False) -> None:
        text = self.keyword_edit.text().strip()
        if not text:
            return
        self.add_token(Token(kind="term", value=text, quoted=bool(exact)))
        self.keyword_edit.clear()

    def _add_operator(self, item: dict) -> None:
        if item.get("raw"):
            template = item.get("template", "{value}")
            if template == "OR":
                if self.query.tokens:
                    self.query.tokens[-1].joiner = "OR"
                    self._refresh()
                    return
                return
            if template == "AND":
                if self.query.tokens:
                    self.query.tokens[-1].joiner = "AND"
                    self._refresh()
                    return
                return
            kind = "group" if item["id"] == "group" else "raw"
            token = Token(kind=kind, value="", label=item["label"])
            if item["id"] == "exact":
                token = Token(kind="term", value="", quoted=True, label="frase")
            self.add_token(token)
            return

        self.add_token(Token(kind="operator", operator=item["token"],
                             value="", label=item["label"]))

    def _add_filetype_groups(self) -> None:
        chosen = [group for group_id, bubble in self._filetype_bubbles.items()
                  if bubble.isChecked()
                  for group in [catalog.filetype_group(group_id)] if group]
        if not chosen:
            message(self, "Nessun gruppo selezionato",
                    "Seleziona almeno un gruppo di tipi di documento.", "warn")
            return
        extensions: list[str] = []
        for group in chosen:
            for extension in group["extensions"]:
                if extension not in extensions:
                    extensions.append(extension)
        token = group_of(extensions, "filetype")
        token.label = "tipi ×%d" % len(extensions)
        self.add_token(token)
        self._clear_filetype_groups()

    def _clear_filetype_groups(self) -> None:
        for bubble in self._filetype_bubbles.values():
            bubble.setChecked(False)

    def _recipe_selected(self) -> None:
        recipe_id = self.recipe_list.currentData()
        while self.recipe_form_layout.count():
            item = self.recipe_form_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._recipe_fields: dict[str, QtWidgets.QLineEdit] = {}

        recipe = catalog.recipe(recipe_id) if recipe_id else None
        if not recipe:
            self.recipe_desc.setText("")
            self.recipe_apply.setEnabled(False)
            return

        self.recipe_desc.setText(recipe["desc"])
        placeholders = catalog.recipe_placeholders()
        for field_name in recipe.get("fields", []):
            spec = placeholders.get(field_name, {})
            edit = QtWidgets.QLineEdit()
            edit.setPlaceholderText(spec.get("hint", field_name))
            edit.returnPressed.connect(self._apply_recipe)
            self.recipe_form_layout.addRow(spec.get("label", field_name), edit)
            self._recipe_fields[field_name] = edit
        self.recipe_apply.setEnabled(True)

    def _apply_recipe(self) -> None:
        recipe_id = self.recipe_list.currentData()
        if not recipe_id:
            return
        values = {name: edit.text() for name, edit in self._recipe_fields.items()}
        missing = [name for name, value in values.items() if not value.strip()]
        if missing:
            message(self, "Campi mancanti",
                    "Completa: %s" % ", ".join(missing), "warn")
            return
        rendered = catalog.render_recipe(recipe_id, values)
        self.set_query_text(rendered)

    # --------------------------------------------------------------- modello
    def add_token(self, token: Token, focus: bool = True) -> None:
        self.query.add(token)
        self._refresh()
        if focus and self._chips:
            self._chips[-1].focus_value()

    def move_token(self, token: Token, delta: int) -> None:
        self.query.move(token, delta)
        self._refresh()

    def _remove_token(self, token: Token) -> None:
        self.query.remove(token)
        self._refresh()

    def clear(self) -> None:
        self.query.clear()
        self._refresh()

    def set_query_text(self, text: str) -> None:
        """Carica una query testuale ricostruendo le bolle."""
        self.query = DorkQuery.from_text(text)
        self._refresh()

    def query_text(self) -> str:
        if self._raw_mode:
            return self.preview.toPlainText().strip()
        return self.query.to_string()

    # -------------------------------------------------------------- refresh
    def _refresh(self) -> None:
        for chip in self._chips:
            chip.setParent(None)
            chip.deleteLater()
        self._chips.clear()
        while self.canvas_layout.count():
            item = self.canvas_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        for token in self.query:
            chip = TokenChip(token, self.canvas)
            chip.changed.connect(self._refresh_preview)
            chip.removed.connect(self._remove_token)
            chip.move_requested.connect(self.move_token)
            self.canvas_layout.addWidget(chip)
            self._chips.append(chip)

        self.empty_hint.setVisible(not self._chips)
        self.token_count.setText("%d token" % len(self.query))
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        if self._raw_mode:
            return
        text = self.query.to_string()
        self.preview.setPlainText(text)
        self.search_button.setEnabled(bool(text))
        self.browser_button.setEnabled(bool(text))
        self.query_changed.emit(text)

    def _toggle_raw(self, enabled: bool) -> None:
        self._raw_mode = enabled
        self.preview.setReadOnly(not enabled)
        self.raw_toggle.setText("Torna alle bolle" if enabled else "Modifica come testo")
        if not enabled:
            self.set_query_text(self.preview.toPlainText())
        else:
            self.preview.setFocus()

    # -------------------------------------------------------------- motori
    def refresh_providers(self) -> None:
        """Ricostruisce l'elenco dei motori tenendo conto delle credenziali."""
        current = self.provider_combo.currentData() or self.config.get("provider")
        self.provider_combo.blockSignals(True)
        self.provider_combo.clear()

        model = self.provider_combo.model()
        for kind in providers.kinds():
            items = providers.by_kind(kind)
            if not items:
                continue
            self.provider_combo.addItem("── %s ──"
                                        % providers.KIND_LABELS[kind], None)
            index = self.provider_combo.count() - 1
            model.item(index).setEnabled(False)
            for provider in items:
                ready = provider.available(self.config)
                suffix = "" if ready else "  (credenziali mancanti)"
                self.provider_combo.addItem(provider.label + suffix, provider.id)
        self.provider_combo.blockSignals(False)

        target = self.provider_combo.findData(current)
        self.provider_combo.setCurrentIndex(target if target >= 0 else 1)
        self._provider_changed()

    def current_provider(self):
        return providers.get(self.provider_combo.currentData() or "")

    def _provider_changed(self) -> None:
        provider = self.current_provider()
        if provider is None:
            return
        self.config.set("provider", provider.id)

        self.kind_badge.setText(providers.KIND_LABELS.get(provider.kind, provider.kind))
        self.kind_badge.set_color({"browser": "#6b7280", "api": "#3d7bff",
                                   "agentic": "#8e44ad"}.get(provider.kind, "#6b7280"))

        self.dork_badge.setText(providers.DORK_LABELS.get(provider.dork_support, ""))
        self.dork_badge.setToolTip(providers.DORK_HELP.get(provider.dork_support, ""))
        self.dork_badge.set_color({"full": "#16a34a", "partial": "#d97706",
                                   "none": "#c0392b"}.get(provider.dork_support, "#6b7280"))

        ready = provider.available(self.config)
        self.status_badge.setText("pronto" if ready else "da configurare")
        self.status_badge.set_color("#16a34a" if ready else "#c0392b")

        hint = provider.description
        if provider.dork_support == providers.DORK_NONE:
            hint += ("\nI vincoli della query vengono tradotti in linguaggio naturale "
                     "e i risultati verificati lato client.")
        if not ready:
            missing = ", ".join(c.label for c in provider.missing_credentials(self.config))
            if missing:
                hint += "\nManca: %s (Impostazioni → Motori)." % missing
        self.provider_hint.setText(hint)

        self.search_button.setEnabled(provider.kind != "browser" and bool(self.query_text()))
        self.search_button.setToolTip(
            "Questo motore si apre nel browser" if provider.kind == "browser" else "")

    # --------------------------------------------------------------- segnali
    def trigger_search(self) -> None:
        """Avvia la ricerca: usato anche dalla barra degli strumenti."""
        self._emit_search()

    def trigger_open(self) -> None:
        """Apre la query nel browser: usato anche dalla barra degli strumenti."""
        self._emit_open()

    def _emit_search(self) -> None:
        text = self.query_text()
        provider = self.current_provider()
        if text and provider:
            self.search_requested.emit(provider.id, text, self.limit_spin.value())

    def _emit_open(self) -> None:
        text = self.query_text()
        provider = self.current_provider()
        if text and provider:
            self.open_requested.emit(provider.id, text)

    def _emit_save(self) -> None:
        text = self.query_text()
        if text:
            self.save_requested.emit(text)

    def _copy(self) -> None:
        text = self.query_text()
        if text:
            QtWidgets.QApplication.clipboard().setText(text)
