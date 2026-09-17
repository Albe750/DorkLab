"""Motori con API di ricerca tradizionale (risultati strutturati)."""

from __future__ import annotations

from urllib.parse import quote_plus, urlparse

from .base import (BaseProvider, Credential, DORK_FULL, DORK_NONE, DORK_PARTIAL,
                   SearchError, SearchResponse, SearchResult)
from .http import get_json


class GoogleCSEProvider(BaseProvider):
    """Google Programmable Search Engine (JSON API ufficiale).

    E' l'unico modo lecito di interrogare Google in modo programmatico: lo
    scraping della pagina dei risultati viola i termini di servizio e viene
    bloccato rapidamente. Il motore personalizzato va configurato per cercare
    su tutto il web perche' i dork funzionino come su google.com.
    """

    id = "google_cse"
    label = "Google Programmable Search (API)"
    kind = "api"
    dork_support = DORK_FULL
    homepage = "https://programmablesearchengine.google.com/"
    description = ("100 query gratuite al giorno. Richiede una chiave API e "
                   "l'ID del motore (cx) configurato su \"cerca in tutto il web\".")
    credentials = [
        Credential("google_api_key", "Chiave API Google",
                   "Console Google Cloud, API \"Custom Search API\"."),
        Credential("google_cx", "ID motore (cx)",
                   "Identificativo del Programmable Search Engine.", secret=False),
    ]
    ENDPOINT = "https://www.googleapis.com/customsearch/v1"
    MAX_RESULTS = 100  # limite imposto dall'API

    def build_url(self, query: str, results_per_page: int = 20) -> str:
        return "https://www.google.com/search?q=%s" % quote_plus(query)

    def search(self, query: str, *, config, limit: int = 20, progress=None) -> SearchResponse:
        key = config.credential("google_api_key")
        cx = config.credential("google_cx")
        if not key or not cx:
            raise SearchError("Chiave API o ID motore (cx) mancanti.")

        limit = min(limit, self.MAX_RESULTS)
        results: list[SearchResult] = []
        start = 1
        truncated = False

        while len(results) < limit:
            batch = min(10, limit - len(results))
            self._note(progress, "Google CSE: risultati %d-%d" % (start, start + batch - 1))
            payload = get_json(self.ENDPOINT, params={
                "key": key, "cx": cx, "q": query,
                "num": batch, "start": start,
            })
            items = payload.get("items") or []
            for item in items:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    provider=self.id,
                    mime=item.get("mime", ""),
                    filetype=(item.get("fileFormat") or "").split()[0].lower().strip("."),
                    raw=item,
                ))
            if len(items) < batch:
                break
            start += batch
            if start > 91:  # l'API non restituisce oltre il centesimo risultato
                truncated = len(results) >= self.MAX_RESULTS
                break

        total = (payload.get("searchInformation") or {}).get("totalResults", "")
        return SearchResponse(provider=self.id, query=query, results=results,
                              truncated=truncated,
                              meta={"totale_stimato": total})


class BraveAPIProvider(BaseProvider):
    """Brave Search API: indice indipendente, piano gratuito disponibile."""

    id = "brave_api"
    label = "Brave Search (API)"
    kind = "api"
    dork_support = DORK_PARTIAL
    homepage = "https://brave.com/search/api/"
    description = "Indice proprietario. Supporta site: e filetype:, non tutti gli operatori Google."
    credentials = [Credential("brave_api_key", "Chiave API Brave",
                              "Piano gratuito: 2000 query al mese.")]
    ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def build_url(self, query: str, results_per_page: int = 20) -> str:
        return "https://search.brave.com/search?q=%s" % quote_plus(query)

    def search(self, query: str, *, config, limit: int = 20, progress=None) -> SearchResponse:
        key = config.credential("brave_api_key")
        if not key:
            raise SearchError("Chiave API Brave mancante.")

        results: list[SearchResult] = []
        offset = 0
        while len(results) < limit and offset <= 9:
            count = min(20, limit - len(results))
            self._note(progress, "Brave: pagina %d" % (offset + 1))
            payload = get_json(self.ENDPOINT,
                               params={"q": query, "count": count, "offset": offset},
                               headers={"Accept": "application/json",
                                        "X-Subscription-Token": key})
            items = (payload.get("web") or {}).get("results") or []
            for item in items:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("description", ""),
                    provider=self.id,
                    published=item.get("age", ""),
                    raw=item,
                ))
            if len(items) < count:
                break
            offset += 1

        return SearchResponse(provider=self.id, query=query, results=results)


class SerpApiProvider(BaseProvider):
    """SerpApi: interroga Google per conto nostro restituendo JSON.

    Utile quando servono i risultati reali di Google con supporto pieno agli
    operatori, senza i limiti del Programmable Search Engine.
    """

    id = "serpapi"
    label = "SerpApi (Google)"
    kind = "api"
    dork_support = DORK_FULL
    homepage = "https://serpapi.com/"
    description = "Risultati Google reali via API a pagamento. Supporto pieno agli operatori."
    credentials = [Credential("serpapi_key", "Chiave SerpApi", "Dashboard SerpApi.")]
    ENDPOINT = "https://serpapi.com/search.json"

    def build_url(self, query: str, results_per_page: int = 20) -> str:
        return "https://www.google.com/search?q=%s" % quote_plus(query)

    def search(self, query: str, *, config, limit: int = 20, progress=None) -> SearchResponse:
        key = config.credential("serpapi_key")
        if not key:
            raise SearchError("Chiave SerpApi mancante.")

        results: list[SearchResult] = []
        start = 0
        while len(results) < limit:
            num = min(20, limit - len(results))
            self._note(progress, "SerpApi: risultati da %d" % start)
            payload = get_json(self.ENDPOINT, params={
                "engine": "google", "q": query, "num": num,
                "start": start, "api_key": key,
            })
            if payload.get("error"):
                raise SearchError(str(payload["error"]))
            items = payload.get("organic_results") or []
            for item in items:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    provider=self.id,
                    published=item.get("date", ""),
                    raw=item,
                ))
            if len(items) < num:
                break
            start += num

        return SearchResponse(provider=self.id, query=query, results=results)


class SearxngProvider(BaseProvider):
    """Istanza SearXNG con formato JSON abilitato.

    Non richiede chiavi: basta l'indirizzo di un'istanza (anche self-hosted,
    la scelta migliore per un uso continuativo).
    """

    id = "searxng"
    label = "SearXNG (istanza propria)"
    kind = "api"
    dork_support = DORK_PARTIAL
    homepage = "https://docs.searxng.org/"
    description = ("Meta-motore self-hosted. Nessuna chiave: serve solo l'URL "
                   "dell'istanza con il formato JSON abilitato in settings.yml.")
    credentials = [Credential("searxng_url", "URL istanza",
                              "Esempio: http://localhost:8888", secret=False)]

    def available(self, config) -> bool:
        return bool(config.credential("searxng_url") or config.get("searxng_url"))

    def _base(self, config) -> str:
        url = config.credential("searxng_url") or config.get("searxng_url") or ""
        return str(url).rstrip("/")

    def build_url(self, query: str, results_per_page: int = 20) -> str:
        return "https://searx.be/search?q=%s" % quote_plus(query)

    def search(self, query: str, *, config, limit: int = 20, progress=None) -> SearchResponse:
        base = self._base(config)
        if not base:
            raise SearchError("URL dell'istanza SearXNG non configurato.")
        if not urlparse(base).scheme:
            base = "http://" + base

        results: list[SearchResult] = []
        page = 1
        while len(results) < limit and page <= 5:
            self._note(progress, "SearXNG: pagina %d" % page)
            payload = get_json(base + "/search", params={
                "q": query, "format": "json", "pageno": page,
            })
            items = payload.get("results") or []
            if not items:
                break
            for item in items:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    provider=self.id,
                    published=item.get("publishedDate", "") or "",
                    score=float(item.get("score") or 0),
                    raw=item,
                ))
            page += 1

        return SearchResponse(provider=self.id, query=query, results=results[:limit])


def api_providers() -> list[BaseProvider]:
    return [GoogleCSEProvider(), SerpApiProvider(), BraveAPIProvider(), SearxngProvider()]
