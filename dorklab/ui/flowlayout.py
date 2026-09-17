"""Layout a flusso: le bolle vanno a capo da sole quando lo spazio finisce."""

from __future__ import annotations

from ..qtcompat import Qt, QtCore, QtWidgets


class FlowLayout(QtWidgets.QLayout):
    """Dispone i widget in orizzontale mandandoli a capo al bordo."""

    def __init__(self, parent=None, margin: int = 0, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: list[QtWidgets.QLayoutItem] = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def __del__(self) -> None:  # pragma: no cover - ciclo di vita Qt
        while self._items:
            self._items.pop()

    # ------------------------------------------------------- API di QLayout
    def addItem(self, item) -> None:  # noqa: N802 - firma Qt
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802 - firma Qt
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):  # noqa: N802 - firma Qt
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):  # noqa: N802 - firma Qt
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - firma Qt
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - firma Qt
        return self._layout(QtCore.QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect) -> None:  # noqa: N802 - firma Qt
        super().setGeometry(rect)
        self._layout(rect, apply=True)

    def sizeHint(self):  # noqa: N802 - firma Qt
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802 - firma Qt
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(margins.left() + margins.right(),
                             margins.top() + margins.bottom())
        return size

    # ------------------------------------------------------------- interno
    def _layout(self, rect, apply: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(),
                                  -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if apply:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()
