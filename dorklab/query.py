"""Modello della query: token, composizione e parsing.

Una query di DorkLab e' una sequenza ordinata di token. Ogni token conosce il
proprio operatore, il valore, se e' negato e come si lega al token precedente
(AND implicito oppure OR esplicito). Questo permette all'interfaccia di
rappresentare ogni pezzo della query come una "bolla" modificabile e di
ricostruire la stringa finale in modo deterministico.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field, asdict
from typing import Iterable, Iterator

#: Operatori con sintassi `operatore:valore`.
PREFIX_OPERATORS = {
    "site", "inurl", "allinurl", "intitle", "allintitle", "intext", "allintext",
    "inanchor", "allinanchor", "filetype", "ext", "related", "cache", "link",
    "info", "define", "before", "after", "daterange", "contains", "ip", "feed",
    "inbody", "domain", "language", "mime", "host", "rhost", "lang", "url",
    "loc", "location", "source", "imagesize", "title",
}

_NEEDS_QUOTES = re.compile(r"[\s()]")


@dataclass
class Token:
    """Un elemento atomico della query."""

    kind: str = "term"           # term | operator | group | raw
    operator: str = ""           # per kind == "operator"
    value: str = ""
    negated: bool = False
    quoted: bool = False
    enabled: bool = True
    joiner: str = "AND"          # legame con il token precedente: AND | OR
    label: str = ""              # etichetta descrittiva mostrata nella bolla

    # ------------------------------------------------------------------ render
    def _render_value(self) -> str:
        value = self.value.strip()
        if not value:
            return ""
        if self.quoted or (_NEEDS_QUOTES.search(value) and self.kind != "group"):
            if not (value.startswith('"') and value.endswith('"')):
                return '"%s"' % value.replace('"', '')
        return value

    def render(self) -> str:
        """Restituisce la rappresentazione testuale del token."""
        if not self.enabled:
            return ""
        prefix = "-" if self.negated else ""
        value = self._render_value()

        if self.kind == "operator":
            if not self.operator:
                return ""
            if not value:
                return ""
            return "%s%s:%s" % (prefix, self.operator, value)
        if self.kind == "group":
            inner = self.value.strip()
            if not inner:
                return ""
            if not (inner.startswith("(") and inner.endswith(")")):
                inner = "(%s)" % inner
            return prefix + inner
        if self.kind == "raw":
            return (prefix + self.value.strip()) if self.value.strip() else ""
        return (prefix + value) if value else ""

    # ------------------------------------------------------------- descrizione
    def describe(self) -> str:
        """Etichetta breve per l'interfaccia."""
        if self.label:
            return self.label
        if self.kind == "operator":
            return "%s:" % self.operator
        if self.kind == "group":
            return "gruppo"
        if self.kind == "term":
            # il valore e' gia' visibile nel campo accanto: nessuna etichetta
            return '""' if self.quoted else ""
        return self.value[:24] or "termine"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Token":
        known = {f for f in cls.__dataclass_fields__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class DorkQuery:
    """Sequenza di token che compone una query completa."""

    tokens: list[Token] = field(default_factory=list)

    # -------------------------------------------------------------- contenitore
    def __iter__(self) -> Iterator[Token]:
        return iter(self.tokens)

    def __len__(self) -> int:
        return len(self.tokens)

    def add(self, token: Token, index: int | None = None) -> Token:
        if index is None:
            self.tokens.append(token)
        else:
            self.tokens.insert(index, token)
        return token

    def remove(self, token: Token) -> None:
        if token in self.tokens:
            self.tokens.remove(token)

    def move(self, token: Token, delta: int) -> None:
        if token not in self.tokens:
            return
        old = self.tokens.index(token)
        new = max(0, min(len(self.tokens) - 1, old + delta))
        if new != old:
            self.tokens.insert(new, self.tokens.pop(old))

    def clear(self) -> None:
        self.tokens.clear()

    # ------------------------------------------------------------------- render
    def to_string(self) -> str:
        """Compone la stringa finale della query."""
        parts: list[str] = []
        for token in self.tokens:
            rendered = token.render()
            if not rendered:
                continue
            if parts and token.joiner == "OR":
                parts.append("OR")
            parts.append(rendered)
        return " ".join(parts).strip()

    def __str__(self) -> str:  # pragma: no cover - comodita'
        return self.to_string()

    # ------------------------------------------------------------ serializzazione
    def to_dict(self) -> dict:
        return {"tokens": [t.to_dict() for t in self.tokens]}

    @classmethod
    def from_dict(cls, data: dict) -> "DorkQuery":
        return cls(tokens=[Token.from_dict(t) for t in data.get("tokens", [])])

    # ------------------------------------------------------------------ fabbrica
    @classmethod
    def from_text(cls, text: str) -> "DorkQuery":
        return cls(tokens=list(parse(text)))


# --------------------------------------------------------------------- parsing
def _split_top_level(text: str) -> list[str]:
    """Divide la stringa in pezzi rispettando virgolette e parentesi."""
    pieces: list[str] = []
    buffer: list[str] = []
    depth = 0
    in_quotes = False

    for char in text:
        if char == '"':
            in_quotes = not in_quotes
            buffer.append(char)
            continue
        if not in_quotes:
            if char == "(":
                depth += 1
                buffer.append(char)
                continue
            if char == ")":
                depth = max(0, depth - 1)
                buffer.append(char)
                continue
            if char.isspace() and depth == 0:
                if buffer:
                    pieces.append("".join(buffer))
                    buffer = []
                continue
        buffer.append(char)

    if buffer:
        pieces.append("".join(buffer))
    return pieces


def parse(text: str) -> list[Token]:
    """Trasforma una query testuale nell'elenco dei token corrispondenti.

    Serve per la modalita' "incolla un dork": l'utente incolla una stringa e
    l'interfaccia la ricostruisce come bolle modificabili.
    """
    tokens: list[Token] = []
    pending_or = False

    for piece in _split_top_level(text.strip()):
        if not piece:
            continue

        upper = piece.upper()
        if upper == "OR" or piece == "|":
            pending_or = True
            continue
        if upper == "AND":
            continue

        joiner = "OR" if pending_or else "AND"
        pending_or = False

        negated = piece.startswith("-")
        if negated:
            piece = piece[1:]
        if not piece:
            continue

        if piece.startswith("(") and piece.endswith(")"):
            tokens.append(Token(kind="group", value=piece[1:-1].strip(),
                                negated=negated, joiner=joiner, label="gruppo"))
            continue

        match = re.match(r"^([A-Za-z_]+):(.*)$", piece, flags=re.DOTALL)
        if match and match.group(1).lower() in PREFIX_OPERATORS:
            operator = match.group(1).lower()
            value = match.group(2)
            quoted = value.startswith('"') and value.endswith('"') and len(value) > 1
            if quoted:
                value = value[1:-1]
            tokens.append(Token(kind="operator", operator=operator, value=value,
                                negated=negated, quoted=quoted, joiner=joiner,
                                label="%s:" % operator))
            continue

        quoted = piece.startswith('"') and piece.endswith('"') and len(piece) > 1
        value = piece[1:-1] if quoted else piece
        tokens.append(Token(kind="term", value=value, negated=negated,
                            quoted=quoted, joiner=joiner))

    return tokens


# ------------------------------------------------------------------- utilities
def group_of(values: Iterable[str], operator: str = "filetype") -> Token:
    """Crea un token gruppo del tipo `(filetype:pdf OR filetype:docx)`."""
    parts = ["%s:%s" % (operator, v.strip()) for v in values if v.strip()]
    return Token(kind="group", value=" OR ".join(parts),
                 label="%s x%d" % (operator, len(parts)))


def quote_if_needed(value: str) -> str:
    value = value.strip()
    if not value:
        return value
    if _NEEDS_QUOTES.search(value) and not value.startswith('"'):
        return '"%s"' % value
    return value


def shlex_terms(text: str) -> list[str]:
    """Estrae i termini liberi da una stringa, ignorando gli operatori."""
    try:
        pieces = shlex.split(text)
    except ValueError:
        pieces = text.split()
    return [p for p in pieces if ":" not in p and p.upper() not in {"OR", "AND"}]
