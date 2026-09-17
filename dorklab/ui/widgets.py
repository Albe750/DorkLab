"""Widget riutilizzabili: bolle, chip modificabili, sezioni richiudibili."""

from __future__ import annotations

from ..qtcompat import Qt, QtCore, QtGui, QtWidgets, Signal
from ..query import Token
from .flowlayout import FlowLayout


class Bubble(QtWidgets.QPushButton):
    """Bolla cliccabile della tavolozza."""

    def __init__(self, text: str, *, tooltip: str = "", checkable: bool = False,
                 sensitive: bool = False, enabled: bool = True, parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("bubbleSensitive" if sensitive else "bubble")
        self.setCheckable(checkable)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setEnabled(enabled)
        if tooltip:
            self.setToolTip(tooltip)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Maximum,
                           QtWidgets.QSizePolicy.Policy.Fixed)
        # Lo stile dello stato selezionato potrebbe usare un font diverso:
        # si riserva fin da subito la larghezza del testo in grassetto, cosi'
        # la selezione non tronca mai l'etichetta.
        bold = QtGui.QFont(self.font())
        bold.setBold(True)
        metrics = QtGui.QFontMetrics(bold)
        self.setMinimumWidth(metrics.horizontalAdvance(text) + 30)
        if checkable:
            self.toggled.connect(lambda _: self.updateGeometry())


class BubbleBar(QtWidgets.QWidget):
    """Contenitore a flusso di bolle."""

    clicked = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._layout = FlowLayout(self, margin=0, spacing=6)
        self._bubbles: list[Bubble] = []

    def add(self, text: str, payload, *, tooltip: str = "", checkable: bool = False,
            sensitive: bool = False, enabled: bool = True) -> Bubble:
        bubble = Bubble(text, tooltip=tooltip, checkable=checkable,
                        sensitive=sensitive, enabled=enabled, parent=self)
        bubble.clicked.connect(lambda _=False, p=payload: self.clicked.emit(p))
        self._layout.addWidget(bubble)
        self._bubbles.append(bubble)
        return bubble

    def bubbles(self) -> list[Bubble]:
        return list(self._bubbles)

    def checked_payloads(self, payloads: dict) -> list:
        return [payloads[b] for b in self._bubbles if b.isChecked() and b in payloads]

    def clear(self) -> None:
        for bubble in self._bubbles:
            bubble.setParent(None)
            bubble.deleteLater()
        self._bubbles.clear()
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()


class TokenChip(QtWidgets.QFrame):
    """Rappresentazione modificabile di un token della query.

    La chip mostra l'operatore, permette di modificarne il valore in linea, di
    negarlo, di cambiarne il legame logico e di rimuoverlo.
    """

    changed = Signal()
    removed = Signal(object)
    move_requested = Signal(object, int)

    def __init__(self, token: Token, parent=None) -> None:
        super().__init__(parent)
        self.token = token
        self.setObjectName("chipNegated" if token.negated else "chip")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(9, 3, 5, 3)
        layout.setSpacing(4)

        self.joiner = QtWidgets.QPushButton(self)
        self.joiner.setObjectName("chipBtn")
        self.joiner.setFixedWidth(26)
        self.joiner.setToolTip("Legame con il token precedente: AND oppure OR")
        self.joiner.clicked.connect(self._toggle_joiner)
        layout.addWidget(self.joiner)

        self.label = QtWidgets.QLabel(token.describe(), self)
        self.label.setObjectName("chipLabel")
        layout.addWidget(self.label)

        # I gruppi contengono un'espressione lunga: mostrarla per intero nella
        # chip la renderebbe illeggibile, quindi si usa un riassunto cliccabile.
        if token.kind == "group":
            self.value = QtWidgets.QLabel(self)
            self.value.setObjectName("chipLabel")
            self.value.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.value = QtWidgets.QLineEdit(token.value, self)
            self.value.setObjectName("chipValue")
            self.value.setPlaceholderText("valore")
            self.value.textChanged.connect(self._on_value)
            self.value.editingFinished.connect(self.changed.emit)
        layout.addWidget(self.value)

        self.negate = QtWidgets.QPushButton("−", self)
        self.negate.setObjectName("chipBtn")
        self.negate.setFixedWidth(18)
        self.negate.setToolTip("Nega questo token (prefisso -)")
        self.negate.clicked.connect(self._toggle_negate)
        layout.addWidget(self.negate)

        close = QtWidgets.QPushButton("×", self)
        close.setObjectName("chipBtn")
        close.setFixedWidth(18)
        close.setToolTip("Rimuovi")
        close.clicked.connect(lambda: self.removed.emit(self.token))
        layout.addWidget(close)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self._sync()

    # --------------------------------------------------------------- interno
    def _sync(self) -> None:
        self.joiner.setText("OR" if self.token.joiner == "OR" else "&")
        description = self.token.describe()
        self.label.setText(description)
        self.label.setVisible(bool(description))
        self.setObjectName("chipNegated" if self.token.negated else "chip")
        self.style().unpolish(self)
        self.style().polish(self)

        if self.token.kind == "group":
            summary = _summarize_group(self.token.value)
            self.value.setText(summary)
            self.value.setToolTip(
                "%s\n\nDoppio clic per modificare il gruppo." % self.token.value)
            self.value.adjustSize()
        else:
            width = max(60, min(230, self.value.fontMetrics()
                                .horizontalAdvance(self.value.text() or "valore") + 24))
            self.value.setFixedWidth(width)
            self.value.setToolTip(self.token.render())

    def _on_value(self, text: str) -> None:
        self.token.value = text
        self._sync()
        self.changed.emit()

    def _toggle_negate(self) -> None:
        self.token.negated = not self.token.negated
        self._sync()
        self.changed.emit()

    def _toggle_joiner(self) -> None:
        self.token.joiner = "OR" if self.token.joiner == "AND" else "AND"
        self._sync()
        self.changed.emit()

    def _menu(self, point) -> None:
        menu = QtWidgets.QMenu(self)
        quoted = menu.addAction("Frase esatta (virgolette)")
        quoted.setCheckable(True)
        quoted.setChecked(self.token.quoted)
        negated = menu.addAction("Nega (-)")
        negated.setCheckable(True)
        negated.setChecked(self.token.negated)
        enabled = menu.addAction("Attivo")
        enabled.setCheckable(True)
        enabled.setChecked(self.token.enabled)
        menu.addSeparator()
        left = menu.addAction("Sposta a sinistra")
        right = menu.addAction("Sposta a destra")
        menu.addSeparator()
        delete = menu.addAction("Rimuovi")

        chosen = menu.exec(self.mapToGlobal(point))
        if chosen is quoted:
            self.token.quoted = quoted.isChecked()
        elif chosen is negated:
            self.token.negated = negated.isChecked()
        elif chosen is enabled:
            self.token.enabled = enabled.isChecked()
            self.setEnabled(True)
            self.value.setStyleSheet("" if self.token.enabled else "color: gray;")
        elif chosen is left:
            self.move_requested.emit(self.token, -1)
            return
        elif chosen is right:
            self.move_requested.emit(self.token, 1)
            return
        elif chosen is delete:
            self.removed.emit(self.token)
            return
        self._sync()
        self.changed.emit()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - firma Qt
        if self.token.kind == "group":
            self._edit_group()
            return
        super().mouseDoubleClickEvent(event)

    def _edit_group(self) -> None:
        """Modifica l'espressione completa di un gruppo in una finestra dedicata."""
        text, ok = QtWidgets.QInputDialog.getText(
            self, "Modifica il gruppo",
            "Espressione tra parentesi:", QtWidgets.QLineEdit.EchoMode.Normal,
            self.token.value)
        if ok:
            self.token.value = text.strip()
            self._sync()
            self.changed.emit()

    def focus_value(self) -> None:
        if isinstance(self.value, QtWidgets.QLineEdit):
            self.value.setFocus()
            self.value.selectAll()


def _summarize_group(expression: str) -> str:
    """Riassume un'espressione di gruppo in una forma leggibile nella chip."""
    expression = (expression or "").strip()
    if not expression:
        return "vuoto"
    parts = [piece.strip() for piece in expression.split(" OR ") if piece.strip()]
    if len(parts) <= 1:
        return expression if len(expression) <= 28 else expression[:26] + "\u2026"
    values = []
    for piece in parts:
        values.append(piece.split(":", 1)[1] if ":" in piece else piece)
    shown = ", ".join(values[:3])
    if len(parts) > 3:
        shown += " +%d" % (len(parts) - 3)
    return shown


class SectionBox(QtWidgets.QWidget):
    """Sezione con intestazione cliccabile che mostra o nasconde il contenuto."""

    def __init__(self, title: str, subtitle: str = "", expanded: bool = True,
                 parent=None) -> None:
        super().__init__(parent)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self.header = QtWidgets.QPushButton(self)
        self.header.setObjectName("linkish")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.clicked.connect(self.toggle)
        outer.addWidget(self.header)

        if subtitle:
            hint = QtWidgets.QLabel(subtitle, self)
            hint.setObjectName("hint")
            hint.setWordWrap(True)
            outer.addWidget(hint)
            self._subtitle = hint
        else:
            self._subtitle = None

        self.body = QtWidgets.QWidget(self)
        outer.addWidget(self.body)

        self._title = title
        self._expanded = expanded
        self._refresh()

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self._refresh()

    def _refresh(self) -> None:
        arrow = "▾" if self._expanded else "▸"
        self.header.setText("%s  %s" % (arrow, self._title))
        self.body.setVisible(self._expanded)
        if self._subtitle is not None:
            self._subtitle.setVisible(self._expanded)


class Badge(QtWidgets.QLabel):
    """Etichetta colorata compatta."""

    def __init__(self, text: str, color: str = "#6b7280", parent=None) -> None:
        super().__init__(text, parent)
        self.set_color(color)

    def set_color(self, color: str) -> None:
        self.setStyleSheet(
            "background: %s22; color: %s; border: 1px solid %s55;"
            "border-radius: 8px; padding: 2px 8px; font-size: 9pt; font-weight: 600;"
            % (color, color, color)
        )


def info_label(text: str, parent=None) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text, parent)
    label.setObjectName("hint")
    label.setWordWrap(True)
    return label


def message(parent, title: str, text: str, icon: str = "info") -> None:
    box = QtWidgets.QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon({
        "info": QtWidgets.QMessageBox.Icon.Information,
        "warn": QtWidgets.QMessageBox.Icon.Warning,
        "error": QtWidgets.QMessageBox.Icon.Critical,
        "ask": QtWidgets.QMessageBox.Icon.Question,
    }.get(icon, QtWidgets.QMessageBox.Icon.Information))
    box.exec()


def confirm(parent, title: str, text: str) -> bool:
    answer = QtWidgets.QMessageBox.question(
        parent, title, text,
        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
        QtWidgets.QMessageBox.StandardButton.No,
    )
    return answer == QtWidgets.QMessageBox.StandardButton.Yes
