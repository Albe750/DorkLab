"""Interfaccia comune a tutti i motori di ricerca supportati.

DorkLab distingue tre famiglie di motori:

``browser``
    Nessuna chiave, nessuna API: DorkLab compone l'URL e lo apre nel browser
    di sistema. Gli operatori dork vengono eseguiti alla lettera dal motore.

``api``
    Ricerca programmatica con risultati strutturati. Richiede una credenziale.
    Il supporto agli operatori dipende dal servizio.

``agentic``
    Motori basati su modelli linguistici che *interpretano* la richiesta,
    navigano e sintetizzano una risposta con citazioni. Non eseguono gli
    operatori alla lettera: DorkLab traduce i vincoli in linguaggio naturale e
    poi verifica i risultati lato client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Protocol

#: Livello di fedelta' nell'esecuzione degli operatori dork.
DORK_FULL = "full"
DORK_PARTIAL = "partial"
DORK_NONE = "none"

DORK_LABELS = {
    DORK_FULL: "dork nativi",
    DORK_PARTIAL: "dork parziali",
    DORK_NONE: "dork interpretati",
}

#: Spiegazione estesa, mostrata come suggerimento.
DORK_HELP = {
    DORK_FULL: "Il motore esegue gli operatori dork alla lettera.",
    DORK_PARTIAL: "Il motore supporta solo una parte degli operatori: "
                  "verifica i risultati.",
    DORK_NONE: "Il motore interpreta la richiesta invece di eseguire gli "
               "operatori. DorkLab traduce i vincoli in linguaggio naturale "
               "e verifica i risultati lato client.",
}

KIND_LABELS = {
    "browser": "Browser",
    "api": "API",
    "agentic": "Agentico",
}


@dataclass
class Credential:
    """Una credenziale richiesta da un motore."""

    key: str
    label: str
    help: str = ""
    secret: bool = True
    required: bool = True


@dataclass
class SearchResult:
    """Un singolo risultato normalizzato."""

    title: str = ""
    url: str = ""
    snippet: str = ""
    provider: str = ""
    mime: str = ""
    filetype: str = ""
    published: str = ""
    score: float = 0.0
    checks: dict = field(default_factory=dict)
    compliance: str = "sconosciuto"
    raw: dict = field(default_factory=dict)

    @property
    def domain(self) -> str:
        from urllib.parse import urlparse

        return urlparse(self.url).netloc


@dataclass
class SearchResponse:
    """Esito di una ricerca."""

    provider: str = ""
    query: str = ""
    results: list[SearchResult] = field(default_factory=list)
    answer: str = ""
    error: str = ""
    truncated: bool = False
    meta: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.error


ProgressFn = Callable[[str], None]


class SearchError(RuntimeError):
    """Errore recuperabile durante una ricerca."""


class Provider(Protocol):  # pragma: no cover - solo tipizzazione
    id: str
    label: str
    kind: str
    dork_support: str
    homepage: str
    credentials: list[Credential]

    def available(self, config) -> bool: ...
    def search(self, query: str, *, config, limit: int,
               progress: ProgressFn | None = None) -> SearchResponse: ...


class BaseProvider:
    """Implementazione di base condivisa."""

    id = ""
    label = ""
    kind = "api"
    dork_support = DORK_PARTIAL
    homepage = ""
    description = ""
    credentials: list[Credential] = []
    #: True se il motore puo' essere aperto nel browser invece che interrogato.
    browsable = False

    def available(self, config) -> bool:
        return all(config.credential(c.key) for c in self.credentials if c.required)

    def missing_credentials(self, config) -> list[Credential]:
        return [c for c in self.credentials if c.required and not config.credential(c.key)]

    def build_url(self, query: str) -> str:
        raise NotImplementedError

    def search(self, query: str, *, config, limit: int = 20,
               progress: ProgressFn | None = None) -> SearchResponse:
        raise NotImplementedError

    # ------------------------------------------------------------------ helper
    def _note(self, progress: ProgressFn | None, message: str) -> None:
        if progress:
            progress(message)
