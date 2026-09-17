"""Motori aperti nel browser di sistema: nessuna chiave richiesta."""

from __future__ import annotations

from urllib.parse import quote_plus

from .base import BaseProvider, DORK_FULL, DORK_PARTIAL, SearchResponse

#: id, etichetta, template URL, fedelta' dork, note
ENGINES = [
    ("google_browser", "Google", "https://www.google.com/search?q={q}&num={n}",
     DORK_FULL, "Supporto completo agli operatori. E' il riferimento per i dork."),
    ("bing_browser", "Bing", "https://www.bing.com/search?q={q}&count={n}",
     DORK_PARTIAL, "Ha operatori propri (contains:, ip:, inbody:) e ignora inurl:."),
    ("duckduckgo_browser", "DuckDuckGo", "https://duckduckgo.com/?q={q}",
     DORK_PARTIAL, "Buona privacy, operatori di base supportati."),
    ("brave_browser", "Brave Search", "https://search.brave.com/search?q={q}",
     DORK_PARTIAL, "Indice indipendente, utile come confronto."),
    ("startpage_browser", "Startpage", "https://www.startpage.com/sp/search?query={q}",
     DORK_FULL, "Risultati Google senza tracciamento: mantiene gli operatori."),
    ("yandex_browser", "Yandex", "https://yandex.com/search/?text={q}",
     DORK_PARTIAL, "Indice diverso, operatori propri (mime:, host:, rhost:)."),
    ("mojeek_browser", "Mojeek", "https://www.mojeek.com/search?q={q}",
     DORK_PARTIAL, "Crawler indipendente, indice piu' piccolo ma non filtrato."),
    ("searx_browser", "SearXNG (istanza pubblica)", "https://searx.be/search?q={q}",
     DORK_PARTIAL, "Meta-motore: aggrega piu' fonti in un unico risultato."),
]


class BrowserProvider(BaseProvider):
    """Compone l'URL di ricerca e lo consegna al browser."""

    kind = "browser"
    browsable = True
    credentials: list = []

    def __init__(self, provider_id: str, label: str, template: str,
                 dork_support: str, description: str) -> None:
        self.id = provider_id
        self.label = label
        self.template = template
        self.dork_support = dork_support
        self.description = description
        self.homepage = template.split("/search")[0].split("/?")[0]

    def available(self, config) -> bool:  # noqa: D102 - sempre disponibile
        return True

    def build_url(self, query: str, results_per_page: int = 20) -> str:
        return self.template.format(q=quote_plus(query), n=results_per_page)

    def search(self, query: str, *, config, limit: int = 20, progress=None) -> SearchResponse:
        """I motori browser non restituiscono risultati strutturati."""
        return SearchResponse(
            provider=self.id,
            query=query,
            error="Questo motore si apre nel browser: usa il pulsante "
                  "\"Apri nel browser\" oppure scegli un motore con API.",
        )


def browser_providers() -> list[BrowserProvider]:
    return [BrowserProvider(*engine) for engine in ENGINES]
