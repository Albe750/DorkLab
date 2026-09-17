"""Sondaggio a dizionario: risorse esposte non collegate da nulla.

Questa fonte prova un elenco curato di percorsi contro il server e riporta
quelli che rispondono. E' l'unico modo per trovare un backup o un file di
configurazione che nessuno linka e che nessun archivio ha mai visto - ma e'
ricognizione **attiva**: interroga direttamente il server con molte richieste.

Per questo richiede la conferma di autorizzazione, esattamente come la scheda
Audit: si sonda solo cio' di cui si e' proprietari o che si e' autorizzati a
verificare. La richiesta e' comunque conservativa: rispetta il ritardo
configurato e non tenta varianti aggressive.
"""

from __future__ import annotations

import time
from urllib.parse import urljoin

from ..constraints import guess_filetype
from ..paths import DATA_DIR
from .base import PROBE, BaseSource, DiscoveredUrl, DiscoveryError, DiscoveryResponse
from .http import get, session

WORDLIST = DATA_DIR / "discovery_paths.txt"


def load_wordlist() -> list[str]:
    entries: list[str] = []
    try:
        with WORDLIST.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#"):
                    entries.append(line)
    except OSError:
        return []
    return entries


class PathProbeSource(BaseSource):
    id = "probe"
    label = "Sondaggio percorsi (autorizzato)"
    kind = PROBE
    description = ("Prova un elenco curato di percorsi (backup, configurazioni, "
                   "directory di documenti) contro il server. Ricognizione attiva: "
                   "richiede l'autorizzazione sul dominio.")
    homepage = ""
    touches_target = True
    requires_authorization = True
    supports_filetypes = False

    def discover(self, target, *, config, limit=1000, filetypes=None,
                 progress=None, authorized=False) -> DiscoveryResponse:
        self._guard_authorization(authorized)

        user_agent = config.get("user_agent")
        delay = max(0.0, float(config.get("request_delay") or 1.0))
        paths = load_wordlist()
        if not paths:
            raise DiscoveryError("Elenco dei percorsi non disponibile.")

        base = "https://%s/" % target
        handle = session(user_agent)
        found: list[DiscoveredUrl] = []
        tested = 0
        total = min(len(paths), limit)

        for path in paths[:limit]:
            tested += 1
            self._note(progress, "Sondaggio %d/%d: /%s" % (tested, total, path))
            url = urljoin(base, path)
            try:
                response = get(url, user_agent=user_agent, handle=handle,
                               timeout=15, stream=True)
                status = response.status_code
                length = response.headers.get("Content-Length", "")
                content_type = response.headers.get("Content-Type", "")
                response.close()
            except DiscoveryError:
                continue

            # Si riportano solo le risposte che indicano una risorsa presente.
            if status in (200, 201, 203, 206, 301, 302, 401, 403):
                found.append(DiscoveredUrl(
                    url=url, source=self.id, status=str(status),
                    mime=content_type.split(";")[0].strip(),
                    filetype=guess_filetype(url, content_type),
                    title="/%s" % path,
                    extra={"lunghezza": length,
                           "accesso": "protetto" if status in (401, 403) else "aperto"},
                ))
            if delay:
                time.sleep(delay)

        return DiscoveryResponse(
            source=self.id, target=target, urls=found,
            meta={"percorsi_provati": tested, "risposte": len(found)},
            note="401/403 indicano una risorsa presente ma protetta: comunque "
                 "un'informazione utile sull'esposizione.")
