"""Interfaccia comune alle fonti di scoperta di contenuto non indicizzato.

La ricerca tradizionale trova solo cio' che un motore ha *deciso* di indicizzare.
Gran parte della documentazione interessante non lo e': e' stata rimossa dal
vivo ma resta in archivio, sta in un sitemap che il sito pubblica ma i motori
ignorano, oppure in una directory aperta non collegata da alcuna pagina.

Le fonti di scoperta si dividono in due classi, con conseguenze diverse:

``archivio``
    Interrogano archivi di terze parti (Wayback Machine, Common Crawl, log di
    Certificate Transparency). Non toccano il server bersaglio: sono libere
    come una ricerca su un motore.

``server``
    Leggono qualcosa dal server bersaglio: i suoi sitemap e robots.txt, oppure
    le directory che espone. Restano lecite perche' leggono contenuto pubblico,
    ma rispettano robots.txt e il ritardo configurato.

``sondaggio``
    Provano attivamente percorsi da un dizionario per scoprire risorse non
    collegate da nulla. E' ricognizione attiva: richiede la stessa conferma di
    autorizzazione della scheda Audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# Classi di fonte
ARCHIVE = "archivio"
SERVER = "server"
PROBE = "sondaggio"

KIND_LABELS = {
    ARCHIVE: "Archivio di terze parti",
    SERVER: "Mappe del sito",
    PROBE: "Sondaggio attivo",
}

KIND_HELP = {
    ARCHIVE: "Interroga un archivio esterno: non tocca il server del dominio.",
    SERVER: "Legge le mappe che il sito pubblica per i crawler (robots.txt, "
            "sitemap.xml) o le directory che espone.",
    PROBE: "Prova percorsi da un dizionario contro il server: e' ricognizione "
           "attiva e richiede la conferma di autorizzazione.",
}

ProgressFn = Callable[[str], None]


class DiscoveryError(RuntimeError):
    """Errore recuperabile durante la scoperta."""


@dataclass
class DiscoveredUrl:
    """Un URL scoperto, eventualmente con la sua copia archiviata."""

    url: str = ""
    source: str = ""
    title: str = ""
    mime: str = ""
    filetype: str = ""
    timestamp: str = ""            # data dello snapshot (archivio) o vuoto
    status: str = ""              # codice HTTP noto, se disponibile
    archived_url: str = ""        # copia recuperabile anche se il vivo e' sparito
    extra: dict = field(default_factory=dict)

    @property
    def domain(self) -> str:
        from urllib.parse import urlparse

        return urlparse(self.url).netloc

    @property
    def has_archive(self) -> bool:
        return bool(self.archived_url)


@dataclass
class DiscoveryResponse:
    """Esito di una scoperta."""

    source: str = ""
    target: str = ""
    urls: list[DiscoveredUrl] = field(default_factory=list)
    error: str = ""
    note: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.error


class BaseSource:
    """Base condivisa dalle fonti di scoperta."""

    id = ""
    label = ""
    kind = ARCHIVE
    description = ""
    homepage = ""
    #: True se la fonte legge qualcosa dal server del dominio.
    touches_target = False
    #: True se la fonte richiede la conferma di autorizzazione.
    requires_authorization = False
    #: True se sa filtrare per tipo di file.
    supports_filetypes = False

    def discover(self, target: str, *, config, limit: int = 500,
                 filetypes: list[str] | None = None,
                 progress: ProgressFn | None = None,
                 authorized: bool = False) -> DiscoveryResponse:
        raise NotImplementedError

    # ------------------------------------------------------------------ helper
    def _note(self, progress: ProgressFn | None, message: str) -> None:
        if progress:
            progress(message)

    def _guard_authorization(self, authorized: bool) -> None:
        if self.requires_authorization and not authorized:
            raise DiscoveryError(
                "Questa fonte esegue ricognizione attiva sul server: conferma "
                "di essere proprietario del dominio o di avere autorizzazione "
                "scritta a verificarlo."
            )
