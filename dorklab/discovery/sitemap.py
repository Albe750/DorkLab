"""robots.txt e sitemap.xml: le mappe che il sito pubblica per i crawler.

Un sitemap elenca URL che il sito vuole far conoscere ai motori, ma che spesso
non risultano comunque indicizzati. robots.txt, al contrario, elenca i percorsi
che il sito chiede di *non* indicizzare: paradossalmente e' una mappa di cio'
che c'e' di piu' interessante. Entrambi sono file pubblicati apposta per essere
letti dai crawler.
"""

from __future__ import annotations

import gzip
import re
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

from ..constraints import guess_filetype
from .base import SERVER, BaseSource, DiscoveredUrl, DiscoveryError, DiscoveryResponse
from .http import get_text

_SITEMAP_RE = re.compile(r"(?im)^\s*sitemap:\s*(\S+)")
_DISALLOW_RE = re.compile(r"(?im)^\s*disallow:\s*(\S+)")
_ALLOW_RE = re.compile(r"(?im)^\s*allow:\s*(\S+)")


class SitemapSource(BaseSource):
    id = "sitemap"
    label = "Sitemap e robots.txt"
    kind = SERVER
    description = ("Legge i sitemap dichiarati dal sito e i percorsi elencati in "
                   "robots.txt: URL noti al sito ma spesso non indicizzati.")
    homepage = ""
    touches_target = True
    supports_filetypes = True

    def discover(self, target, *, config, limit=1000, filetypes=None,
                 progress=None, authorized=False) -> DiscoveryResponse:
        user_agent = config.get("user_agent")
        base = "https://%s" % target
        found: dict[str, DiscoveredUrl] = {}
        notes: list[str] = []

        # 1) robots.txt: percorsi dichiarati e sitemap referenziati
        self._note(progress, "Lettura di robots.txt")
        sitemaps: list[str] = []
        try:
            status, body = get_text(base + "/robots.txt", user_agent=user_agent,
                                    max_bytes=1_000_000)
            if status < 400 and body:
                text = body.decode("utf-8", "replace")
                sitemaps = _SITEMAP_RE.findall(text)
                for path in set(_DISALLOW_RE.findall(text) + _ALLOW_RE.findall(text)):
                    path = path.strip()
                    if path in {"", "/", "*"}:
                        continue
                    url = urljoin(base + "/", path.lstrip("/").replace("*", ""))
                    self._add(found, url, "robots.txt", filetypes)
                notes.append("robots.txt letto")
        except DiscoveryError:
            notes.append("robots.txt non raggiungibile")

        # 2) sitemap: quelli dichiarati piu' la posizione standard
        if not sitemaps:
            sitemaps = [base + "/sitemap.xml", base + "/sitemap_index.xml"]

        visited: set[str] = set()
        queue = list(dict.fromkeys(sitemaps))
        while queue and len(found) < limit:
            sitemap_url = queue.pop(0)
            if sitemap_url in visited:
                continue
            visited.add(sitemap_url)
            self._note(progress, "Lettura sitemap: %s" % sitemap_url[:70])
            child_sitemaps, entries = self._read_sitemap(sitemap_url, user_agent)
            for url in entries:
                self._add(found, url, "sitemap", filetypes)
                if len(found) >= limit:
                    break
            for child in child_sitemaps:
                if child not in visited and len(visited) < 50:
                    queue.append(child)

        if visited and any(v for v in visited):
            notes.append("%d sitemap esaminati" % len(visited))

        return DiscoveryResponse(
            source=self.id, target=target, urls=list(found.values()),
            note="; ".join(notes) or "Nessuna mappa trovata.",
            meta={"url": len(found)})

    def _read_sitemap(self, url: str, user_agent: str) -> tuple[list[str], list[str]]:
        try:
            status, body = get_text(url, user_agent=user_agent, max_bytes=15_000_000)
        except DiscoveryError:
            return [], []
        if status >= 400 or not body:
            return [], []
        if url.endswith(".gz") or body[:2] == b"\x1f\x8b":
            try:
                body = gzip.decompress(body)
            except OSError:
                return [], []
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError:
            return [], []

        tag = root.tag.rsplit("}", 1)[-1]
        locations = [element.text.strip() for element in root.iter()
                     if element.tag.rsplit("}", 1)[-1] == "loc" and element.text]
        if tag == "sitemapindex":
            return locations, []
        return [], locations

    def _add(self, found: dict, url: str, source: str,
             filetypes: list[str] | None) -> None:
        key = url.rstrip("/").lower()
        if not key or key in found:
            return
        filetype = guess_filetype(url)
        if filetypes and filetype not in filetypes:
            return
        found[key] = DiscoveredUrl(url=url, source=self.id, filetype=filetype,
                                   extra={"origine": source})
