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

import random
import string
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

    def _probe(self, url, *, user_agent, handle, follow=True):
        """Interroga un percorso e restituisce (stato, tipo, lunghezza)."""
        try:
            response = get(url, user_agent=user_agent, handle=handle, timeout=15,
                           stream=True, allow_redirects=follow)
            status = response.status_code
            ctype = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            length = response.headers.get("Content-Length", "")
            response.close()
            return status, ctype, length
        except DiscoveryError:
            return None, "", ""

    def _baseline(self, base, *, user_agent, handle):
        """Capisce se il sito risponde 200 anche a percorsi inesistenti (soft-404).

        Interroga due percorsi casuali improbabili: se il server risponde 2xx,
        allora il suo 200 non prova nulla e va confrontato caso per caso.
        """
        soft = False
        types: set[str] = set()
        lengths: set[str] = set()
        for _ in range(2):
            token = "dorklab-" + "".join(
                random.choices(string.ascii_lowercase + string.digits, k=18))
            status, ctype, length = self._probe(
                urljoin(base, token + "-nonesiste.xyzq"),
                user_agent=user_agent, handle=handle)
            if status is not None and 200 <= status < 300:
                soft = True
                types.add(ctype)
                lengths.add(length)
        return soft, types, lengths

    def discover(self, target, *, config, limit=1000, filetypes=None,
                 progress=None, authorized=False) -> DiscoveryResponse:
        self._guard_authorization(authorized)

        user_agent = config.effective_user_agent()
        paths = load_wordlist()
        if not paths:
            raise DiscoveryError("Elenco dei percorsi non disponibile.")

        base = "https://%s/" % target
        handle = session(user_agent)

        self._note(progress, "Verifica del comportamento sui 404 (baseline)")
        soft404, base_types, base_lengths = self._baseline(
            base, user_agent=user_agent, handle=handle)

        found: list[DiscoveredUrl] = []
        tested = 0
        skipped_soft = 0
        total = min(len(paths), limit)

        for path in paths[:limit]:
            tested += 1
            self._note(progress, "Sondaggio %d/%d: /%s" % (tested, total, path))
            status, ctype, length = self._probe(
                urljoin(base, path), user_agent=user_agent, handle=handle)
            time.sleep(config.jittered_delay())
            if status is None:
                continue

            url = urljoin(base, path)
            is_file = bool(ctype) and not ctype.startswith(("text/html", "text/plain"))
            protected = status in (401, 403)
            redirect = status in (301, 302, 307, 308)

            report = False
            note = "aperto"
            if protected:
                # una risorsa protetta esiste: informazione utile sull'esposizione
                report, note = True, "protetto"
            elif 200 <= status < 300:
                if soft404:
                    # il sito risponde 200 a tutto: si segnala solo se il
                    # contenuto e' diverso dalla pagina generica (un vero file,
                    # o una lunghezza chiaramente diversa dal baseline)
                    if is_file:
                        report, note = True, "file"
                    elif length and length not in base_lengths and length != "0":
                        report, note = True, "contenuto diverso"
                    else:
                        skipped_soft += 1
                else:
                    report, note = True, ("file" if is_file else "pagina")
            elif redirect and not soft404:
                report, note = True, "redirect"

            if not report:
                continue

            filetype = guess_filetype(url, ctype)
            if filetypes and filetype not in filetypes:
                continue
            found.append(DiscoveredUrl(
                url=url, source=self.id, status=str(status),
                mime=ctype, filetype=filetype, title="/%s" % path,
                extra={"lunghezza": length, "accesso": note}))

        note = ("401/403 = risorsa presente ma protetta. ")
        if soft404:
            note += ("Attenzione: il sito risponde 200 anche a percorsi "
                     "inesistenti (soft-404); esclusi %d falsi positivi, "
                     "riportati solo i contenuti diversi dalla pagina generica."
                     % skipped_soft)
        return DiscoveryResponse(
            source=self.id, target=target, urls=found,
            meta={"percorsi_provati": tested, "risposte": len(found),
                  "soft_404": "si" if soft404 else "no",
                  "falsi_positivi_esclusi": skipped_soft},
            note=note)
