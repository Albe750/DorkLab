"""Operazioni lunghe eseguite fuori dal thread dell'interfaccia."""

from __future__ import annotations

from ..qtcompat import QtCore, Signal
from .. import providers
from .. import discovery
from ..fetcher import Downloader
from ..metadata import extract as extract_metadata


class SearchWorker(QtCore.QThread):
    """Esegue una o piu' query su un motore e restituisce i risultati."""

    progress = Signal(str)
    finished_ok = Signal(object)          # SearchResponse
    failed = Signal(str)

    def __init__(self, provider_id: str, query: str, config, limit: int = 20,
                 parent=None) -> None:
        super().__init__(parent)
        self.provider_id = provider_id
        self.query = query
        self.config = config
        self.limit = limit

    def run(self) -> None:  # pragma: no cover - thread
        provider = providers.get(self.provider_id)
        if provider is None:
            self.failed.emit("Motore sconosciuto: %s" % self.provider_id)
            return
        try:
            response = provider.search(self.query, config=self.config,
                                       limit=self.limit,
                                       progress=self.progress.emit)
            self.finished_ok.emit(providers.annotate(response))
        except providers.SearchError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - nessun errore deve far cadere la GUI
            self.failed.emit("Errore imprevisto: %s" % exc)


class BatchSearchWorker(QtCore.QThread):
    """Esegue una lista di query in sequenza (usato dall'audit difensivo)."""

    progress = Signal(int, int, str)      # indice, totale, query
    one_done = Signal(int, object)        # indice, SearchResponse
    one_failed = Signal(int, str)
    finished_all = Signal()

    def __init__(self, provider_id: str, queries: list[str], config,
                 limit: int = 10, parent=None) -> None:
        super().__init__(parent)
        self.provider_id = provider_id
        self.queries = queries
        self.config = config
        self.limit = limit
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:  # pragma: no cover - thread
        provider = providers.get(self.provider_id)
        if provider is None:
            self.one_failed.emit(0, "Motore sconosciuto")
            self.finished_all.emit()
            return

        total = len(self.queries)
        for index, query in enumerate(self.queries):
            if self._stop:
                break
            self.progress.emit(index + 1, total, query)
            try:
                response = provider.search(query, config=self.config, limit=self.limit)
                self.one_done.emit(index, providers.annotate(response))
            except providers.SearchError as exc:
                self.one_failed.emit(index, str(exc))
            except Exception as exc:  # noqa: BLE001
                self.one_failed.emit(index, "Errore imprevisto: %s" % exc)
        self.finished_all.emit()


class DownloadWorker(QtCore.QThread):
    """Scarica i documenti selezionati ed estrae i metadati."""

    progress = Signal(int, int, str)
    finished_all = Signal(list, list)     # esiti, metadati
    failed = Signal(str)

    def __init__(self, urls: list[str], config, extract_meta: bool = True,
                 directory: str = "", parent=None) -> None:
        super().__init__(parent)
        self.urls = urls
        self.config = config
        self.extract_meta = extract_meta
        # cartella scelta dall'utente; se vuota si usa quella predefinita
        self.directory = directory
        self._downloader: Downloader | None = None

    def stop(self) -> None:
        if self._downloader:
            self._downloader.cancel()

    def run(self) -> None:  # pragma: no cover - thread
        try:
            self._downloader = Downloader(
                self.directory or self.config.download_path(),
                user_agent=self.config.get("user_agent"),
                delay=self.config.number("request_delay", 1.0),
                respect_robots=bool(self.config.get("respect_robots", True)),
                max_mb=int(self.config.get("max_download_mb") or 50),
            )
            outcomes = self._downloader.fetch_all(self.urls, progress=self.progress.emit)
            metadata = []
            if self.extract_meta:
                for outcome in outcomes:
                    if outcome.ok and outcome.path:
                        entry = extract_metadata(outcome.path)
                        entry["file"] = outcome.path
                        entry["url"] = outcome.url
                        metadata.append(entry)
            self.finished_all.emit(outcomes, metadata)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class ExtractWorker(QtCore.QThread):
    """Estrazione approfondita del contenuto testuale tramite Tavily."""

    progress = Signal(str)
    finished_ok = Signal(dict)
    failed = Signal(str)

    def __init__(self, urls: list[str], config, parent=None) -> None:
        super().__init__(parent)
        self.urls = urls
        self.config = config

    def run(self) -> None:  # pragma: no cover - thread
        provider = providers.get("tavily")
        if provider is None or not hasattr(provider, "extract_content"):
            self.failed.emit("Estrazione disponibile solo con il motore Tavily.")
            return
        try:
            content = provider.extract_content(self.urls, config=self.config,
                                               progress=self.progress.emit)
            self.finished_ok.emit(content)
        except providers.SearchError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001
            self.failed.emit("Errore imprevisto: %s" % exc)


class DiscoveryWorker(QtCore.QThread):
    """Esegue le fonti di scoperta selezionate su un dominio."""

    progress = Signal(str)
    one_done = Signal(str, object)        # source_id, DiscoveryResponse
    one_failed = Signal(str, str)         # source_id, errore
    finished_all = Signal()

    def __init__(self, source_ids, target, config, limit=1000,
                 filetypes=None, authorized=False, parent=None) -> None:
        super().__init__(parent)
        self.source_ids = source_ids
        self.target = target
        self.config = config
        self.limit = limit
        self.filetypes = filetypes or []
        self.authorized = authorized
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:  # pragma: no cover - thread
        for source_id in self.source_ids:
            if self._stop:
                break
            source = discovery.get(source_id)
            if source is None:
                continue
            self.progress.emit("%s\u2026" % source.label)
            try:
                response = source.discover(
                    self.target, config=self.config, limit=self.limit,
                    filetypes=self.filetypes or None,
                    progress=self.progress.emit, authorized=self.authorized)
                self.one_done.emit(source_id, response)
            except discovery.DiscoveryError as exc:
                self.one_failed.emit(source_id, str(exc))
            except Exception as exc:  # noqa: BLE001
                self.one_failed.emit(source_id, "Errore imprevisto: %s" % exc)
        self.finished_all.emit()


class FingerprintWorker(QtCore.QThread):
    """Analizza la tecnologia del sito (URL + una richiesta alle intestazioni)."""

    finished_ok = Signal(object)          # FingerprintReport
    failed = Signal(str)

    def __init__(self, domain, urls, config, parent=None) -> None:
        super().__init__(parent)
        self.domain = domain
        self.urls = urls
        self.config = config

    def run(self) -> None:  # pragma: no cover - thread
        try:
            from .. import fingerprint
            report = fingerprint.analyze(self.domain, self.urls, self.config, probe=True)
            self.finished_ok.emit(report)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
