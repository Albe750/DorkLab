"""Wayback Machine: URL storici di un dominio, anche non piu' online.

E' la fonte piu' potente per il contenuto non indicizzato. L'API CDX di
archive.org restituisce *tutti* gli URL mai archiviati per un dominio, con la
data dello snapshot: documenti rimossi dal sito, versioni vecchie, pagine che
Google ha deindicizzato. E, cosa decisiva, di ognuno esiste una **copia
recuperabile** anche quando il vivo non risponde piu'.
"""

from __future__ import annotations

from urllib.parse import quote

from ..constraints import guess_filetype
from .base import ARCHIVE, BaseSource, DiscoveredUrl, DiscoveryError, DiscoveryResponse
from .http import get_json

CDX_ENDPOINT = "http://web.archive.org/cdx/search/cdx"


def snapshot_url(timestamp: str, original: str) -> str:
    """Costruisce l'URL della copia archiviata grezza (senza barra di navigazione)."""
    return "http://web.archive.org/web/%sid_/%s" % (timestamp, original)


class WaybackSource(BaseSource):
    id = "wayback"
    label = "Wayback Machine (Internet Archive)"
    kind = ARCHIVE
    description = ("Tutti gli URL mai archiviati per il dominio, con la data e la "
                   "copia recuperabile anche se la pagina non e' piu' online.")
    homepage = "https://web.archive.org/"
    touches_target = False
    supports_filetypes = True

    def discover(self, target, *, config, limit=500, filetypes=None,
                 progress=None, authorized=False) -> DiscoveryResponse:
        user_agent = config.get("user_agent")
        self._note(progress, "Wayback Machine: interrogazione dell'indice CDX")

        params = {
            "url": "%s/*" % target,
            "output": "json",
            "fl": "original,timestamp,mimetype,statuscode,digest",
            "collapse": "urlkey",         # un solo snapshot per URL distinto
            "limit": str(min(limit, 50000)),
        }
        # L'API accetta filtri regex sul MIME: piu' efficiente che filtrare dopo.
        if filetypes:
            mimes = _mime_filter(filetypes)
            if mimes:
                params["filter"] = "mimetype:%s" % mimes

        try:
            rows = get_json(CDX_ENDPOINT, user_agent=user_agent, params=params, timeout=60)
        except DiscoveryError:
            raise
        if not rows or len(rows) < 2:
            return DiscoveryResponse(source=self.id, target=target, urls=[],
                                     note="Nessuno snapshot trovato in archivio.")

        header = rows[0]
        index = {name: pos for pos, name in enumerate(header)}
        urls: list[DiscoveredUrl] = []
        seen: set[str] = set()

        for row in rows[1:]:
            original = row[index.get("original", 0)]
            key = original.rstrip("/").lower()
            if not original or key in seen:
                continue
            seen.add(key)
            timestamp = row[index.get("timestamp", 1)] if "timestamp" in index else ""
            mime = row[index.get("mimetype", 2)] if "mimetype" in index else ""
            status = row[index.get("statuscode", 3)] if "statuscode" in index else ""
            filetype = guess_filetype(original, mime)
            if filetypes and filetype not in filetypes:
                continue
            urls.append(DiscoveredUrl(
                url=original, source=self.id, mime=mime, filetype=filetype,
                timestamp=timestamp, status=status,
                archived_url=snapshot_url(timestamp, original) if timestamp else "",
                extra={"digest": row[index.get("digest", -1)] if "digest" in index else ""},
            ))
            if len(urls) >= limit:
                break

        return DiscoveryResponse(
            source=self.id, target=target, urls=urls,
            meta={"snapshot": len(urls),
                  "nota": "Ogni voce ha una copia archiviata scaricabile."},
        )


def _mime_filter(filetypes: list[str]) -> str:
    """Traduce un elenco di estensioni in una regex di MIME per l'API CDX."""
    mapping = {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd\\.openxmlformats.*word.*",
        "xls": "application/vnd\\.ms-excel",
        "xlsx": "application/vnd\\.openxmlformats.*sheet.*",
        "ppt": "application/vnd\\.ms-powerpoint",
        "pptx": "application/vnd\\.openxmlformats.*presentation.*",
        "csv": "text/csv",
        "json": "application/json",
        "xml": "(text|application)/xml",
        "txt": "text/plain",
        "zip": "application/zip",
    }
    parts = [mapping[ext] for ext in filetypes if ext in mapping]
    if not parts:
        return ""
    return "(%s)" % "|".join(parts)
