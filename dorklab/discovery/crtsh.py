"""Certificate Transparency: sottodomini da crt.sh.

Ogni certificato TLS emesso finisce nei log pubblici di Certificate
Transparency. Interrogarli rivela sottodomini che spesso non sono indicizzati
da nessun motore: ambienti di staging, portali interni, servizi dimenticati.
Non tocca il server del dominio: legge un registro pubblico.
"""

from __future__ import annotations

import re

from .base import ARCHIVE, BaseSource, DiscoveredUrl, DiscoveryError, DiscoveryResponse
from .http import get_json

ENDPOINT = "https://crt.sh/"
_HOST_RE = re.compile(r"^[A-Za-z0-9*._-]+$")


class CrtShSource(BaseSource):
    id = "crtsh"
    label = "Certificate Transparency (crt.sh)"
    kind = ARCHIVE
    description = ("Sottodomini ricavati dai log pubblici dei certificati TLS. "
                   "Rivela host non indicizzati: staging, portali interni, servizi.")
    homepage = "https://crt.sh/"
    touches_target = False
    supports_filetypes = False

    def discover(self, target, *, config, limit=500, filetypes=None,
                 progress=None, authorized=False) -> DiscoveryResponse:
        user_agent = config.effective_user_agent()
        self._note(progress, "crt.sh: interrogazione dei log di Certificate Transparency")

        records = get_json(ENDPOINT, user_agent=user_agent,
                           params={"q": "%%.%s" % target, "output": "json"},
                           timeout=60)
        if not isinstance(records, list):
            raise DiscoveryError("Risposta inattesa da crt.sh.")

        hosts: set[str] = set()
        for record in records:
            value = record.get("name_value", "") if isinstance(record, dict) else ""
            for name in value.splitlines():
                name = name.strip().lower().lstrip("*.")
                if name and name.endswith(target.lower()) and _HOST_RE.match(name):
                    hosts.add(name)

        urls = [
            DiscoveredUrl(url="https://%s/" % host, source=self.id, title=host,
                          extra={"host": host})
            for host in sorted(hosts)[:limit]
        ]
        return DiscoveryResponse(
            source=self.id, target=target, urls=urls,
            meta={"sottodomini": len(urls)},
            note="Ogni host puo' essere a sua volta scoperto in profondita'.")
