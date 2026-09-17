"""Crawler di directory aperte: file non collegati da alcuna pagina.

Quando un web server ha l'autoindex attivo, espone l'elenco di una cartella
anche se nessuna pagina la collega. Camminando ricorsivamente in questi indici
si raccolgono file che nessun motore ha mai visto, perche' non esiste un link
che vi punti. Il crawler legge solo cio' che il server *elenca* di sua volonta',
rispetta robots.txt e usa il ritardo configurato.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlparse
from urllib.robotparser import RobotFileParser

from ..constraints import guess_filetype
from .base import SERVER, BaseSource, DiscoveredUrl, DiscoveryError, DiscoveryResponse
from .http import get_text

# Titoli tipici di una pagina di listing generata dal web server.
_INDEX_MARKERS = re.compile(
    r"(?i)<title>\s*index of\b|>\s*\[to parent directory\]|>\s*parent directory\s*<")


class _LinkExtractor(HTMLParser):
    """Estrae gli href da una pagina di directory listing."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):  # noqa: D102
        if tag == "a":
            for name, value in attrs:
                if name == "href" and value:
                    self.links.append(value)


class DirectoryCrawlSource(BaseSource):
    id = "opendir"
    label = "Directory aperte (crawler)"
    kind = SERVER
    description = ("Cammina ricorsivamente nelle directory che il server espone "
                   "con l'autoindex, raccogliendo file non collegati da alcuna pagina.")
    homepage = ""
    touches_target = True
    supports_filetypes = True

    MAX_PAGES = 300     # tetto di pagine di listing da visitare
    MAX_DEPTH = 6

    def discover(self, target, *, config, limit=1000, filetypes=None,
                 progress=None, authorized=False) -> DiscoveryResponse:
        import time

        user_agent = config.effective_user_agent()
        respect_robots = bool(config.get("respect_robots", True))

        # Punto di partenza: la radice del dominio, piu' alcune cartelle comuni
        # di documenti; il crawler procede solo dove trova un vero listing.
        base = "https://%s" % target
        seeds = [base + "/"] + [base + "/%s/" % d for d in
                                ("uploads", "files", "documents", "docs", "download",
                                 "media", "wp-content/uploads", "sites/default/files")]

        robots = _robots(base, user_agent) if respect_robots else None
        found: dict[str, DiscoveredUrl] = {}
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(url, 0) for url in dict.fromkeys(seeds)]
        pages = 0
        listings = 0

        while queue and pages < self.MAX_PAGES and len(found) < limit:
            url, depth = queue.pop(0)
            if url in visited or depth > self.MAX_DEPTH:
                continue
            visited.add(url)
            if robots is not None and not _allowed(robots, user_agent, url):
                continue

            self._note(progress, "Analisi: %s" % url[:70])
            pages += 1
            try:
                status, body = get_text(url, user_agent=user_agent, max_bytes=3_000_000)
            except DiscoveryError:
                continue
            if status >= 400 or not body:
                continue
            text = body.decode("utf-8", "replace")
            if not _INDEX_MARKERS.search(text):
                continue  # non e' una directory aperta: non si prosegue

            listings += 1
            extractor = _LinkExtractor()
            try:
                extractor.feed(text)
            except Exception:  # noqa: BLE001 - HTML malformato
                pass

            for href in extractor.links:
                if href.startswith(("?", "#")) or href in ("../", "..", "/"):
                    continue
                child = urljoin(url, href)
                if urlparse(child).netloc != urlparse(base).netloc:
                    continue
                if not child.startswith(base):
                    continue
                if child.endswith("/"):
                    if child not in visited:
                        queue.append((child, depth + 1))
                else:
                    key = child.rstrip("/").lower()
                    if key in found:
                        continue
                    filetype = guess_filetype(child)
                    if filetypes and filetype not in filetypes:
                        continue
                    found[key] = DiscoveredUrl(
                        url=child, source=self.id, filetype=filetype,
                        title=unquote(child.rsplit("/", 1)[-1]),
                        extra={"directory": url})
            time.sleep(config.jittered_delay())

        note = ("%d directory aperte trovate su %d pagine analizzate"
                % (listings, pages)) if pages else "Nessun punto di partenza raggiungibile."
        return DiscoveryResponse(source=self.id, target=target,
                                 urls=list(found.values()), note=note,
                                 meta={"directory_aperte": listings, "pagine": pages})


def _robots(base: str, user_agent: str):
    parser = RobotFileParser()
    parser.set_url(base + "/robots.txt")
    try:
        parser.read()
    except Exception:  # noqa: BLE001
        return None
    return parser


def _allowed(parser, user_agent: str, url: str) -> bool:
    try:
        return parser.can_fetch(user_agent, url)
    except Exception:  # noqa: BLE001
        return True
