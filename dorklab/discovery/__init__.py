"""Registro delle fonti di scoperta di contenuto non indicizzato."""

from __future__ import annotations

from ..constraints import guess_filetype
from ..providers.base import SearchResult
from .base import (ARCHIVE, BaseSource, DiscoveredUrl, DiscoveryError,
                   DiscoveryResponse, KIND_HELP, KIND_LABELS, PROBE, SERVER)
from .commoncrawl import CommonCrawlSource
from .crawler import DirectoryCrawlSource
from .crtsh import CrtShSource
from .probe import PathProbeSource
from .sitemap import SitemapSource
from .wayback import WaybackSource

_REGISTRY: dict[str, BaseSource] = {}


def _build() -> dict[str, BaseSource]:
    if not _REGISTRY:
        for source in (WaybackSource(), CommonCrawlSource(), CrtShSource(),
                       SitemapSource(), DirectoryCrawlSource(), PathProbeSource()):
            _REGISTRY[source.id] = source
    return _REGISTRY


def all_sources() -> list[BaseSource]:
    return list(_build().values())


def get(source_id: str) -> BaseSource | None:
    return _build().get(source_id)


def by_kind(kind: str) -> list[BaseSource]:
    return [s for s in all_sources() if s.kind == kind]


def kinds() -> list[str]:
    return [ARCHIVE, SERVER, PROBE]


def to_search_results(response: DiscoveryResponse, prefer_archived: bool = False
                      ) -> list[SearchResult]:
    """Converte una risposta di scoperta in risultati riutilizzabili altrove.

    Cosi' il contenuto scoperto passa dalla stessa pipeline di download e
    di estrazione dei metadati dei risultati di ricerca.
    """
    results: list[SearchResult] = []
    for item in response.urls:
        url = item.archived_url if (prefer_archived and item.archived_url) else item.url
        results.append(SearchResult(
            title=item.title or item.url,
            url=url,
            snippet=_describe(item),
            provider="discovery:%s" % item.source,
            mime=item.mime,
            filetype=item.filetype or guess_filetype(url, item.mime),
            published=item.timestamp,
            raw={"live": item.url, "archiviato": item.archived_url,
                 "stato": item.status, **item.extra},
        ))
    return results


def _describe(item: DiscoveredUrl) -> str:
    parts = []
    if item.timestamp:
        parts.append("snapshot %s" % item.timestamp)
    if item.status:
        parts.append("HTTP %s" % item.status)
    if item.has_archive:
        parts.append("copia archiviata disponibile")
    if item.extra.get("directory"):
        parts.append("in %s" % item.extra["directory"])
    return " · ".join(parts)


def dedupe(responses: list[DiscoveryResponse]) -> list[DiscoveredUrl]:
    """Unisce piu' risposte eliminando gli URL duplicati (l'archivio vince)."""
    merged: dict[str, DiscoveredUrl] = {}
    for response in responses:
        for item in response.urls:
            key = item.url.rstrip("/").lower()
            if not key:
                continue
            existing = merged.get(key)
            if existing is None or (item.has_archive and not existing.has_archive):
                merged[key] = item
    return list(merged.values())


__all__ = [
    "all_sources", "get", "by_kind", "kinds", "to_search_results", "dedupe",
    "BaseSource", "DiscoveredUrl", "DiscoveryError", "DiscoveryResponse",
    "KIND_LABELS", "KIND_HELP", "ARCHIVE", "SERVER", "PROBE",
]
