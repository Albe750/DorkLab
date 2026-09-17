"""Common Crawl: URL del dominio presenti nel piu' grande corpus web pubblico.

Complementare alla Wayback Machine: copre pagine che il crawler di Common Crawl
ha raccolto e che spesso non compaiono negli indici dei motori commerciali.
"""

from __future__ import annotations

import json

from ..constraints import guess_filetype
from .base import ARCHIVE, BaseSource, DiscoveredUrl, DiscoveryError, DiscoveryResponse
from .http import get, get_json

COLLINFO = "https://index.commoncrawl.org/collinfo.json"


class CommonCrawlSource(BaseSource):
    id = "commoncrawl"
    label = "Common Crawl"
    kind = ARCHIVE
    description = ("Indice del corpus Common Crawl: URL raccolti dal crawler "
                   "pubblico, spesso assenti dagli indici commerciali.")
    homepage = "https://commoncrawl.org/"
    touches_target = False
    supports_filetypes = True

    def discover(self, target, *, config, limit=500, filetypes=None,
                 progress=None, authorized=False) -> DiscoveryResponse:
        user_agent = config.effective_user_agent()
        self._note(progress, "Common Crawl: individuazione dell'indice piu' recente")

        indexes = get_json(COLLINFO, user_agent=user_agent, timeout=40)
        if not indexes:
            raise DiscoveryError("Impossibile ottenere l'elenco degli indici.")
        api = indexes[0].get("cdx-api")
        if not api:
            raise DiscoveryError("Indice Common Crawl non disponibile.")

        self._note(progress, "Common Crawl: interrogazione di %s" % indexes[0].get("id", ""))
        response = get(api, user_agent=user_agent,
                       params={"url": "%s/*" % target, "output": "json",
                               "limit": str(min(limit * 3, 10000))},
                       timeout=90, stream=True)
        if response.status_code == 404:
            return DiscoveryResponse(source=self.id, target=target, urls=[],
                                     note="Nessun URL indicizzato in questo blocco.")
        if response.status_code >= 400:
            raise DiscoveryError("Errore HTTP %s da Common Crawl" % response.status_code)

        urls: list[DiscoveredUrl] = []
        seen: set[str] = set()
        for line in response.iter_lines():
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            original = record.get("url", "")
            key = original.rstrip("/").lower()
            if not original or key in seen:
                continue
            seen.add(key)
            mime = record.get("mime", "") or record.get("mime-detected", "")
            filetype = guess_filetype(original, mime)
            if filetypes and filetype not in filetypes:
                continue
            urls.append(DiscoveredUrl(
                url=original, source=self.id, mime=mime, filetype=filetype,
                timestamp=record.get("timestamp", ""),
                status=str(record.get("status", "")),
            ))
            if len(urls) >= limit:
                break
        response.close()

        return DiscoveryResponse(source=self.id, target=target, urls=urls,
                                 meta={"indice": indexes[0].get("id", "")})
