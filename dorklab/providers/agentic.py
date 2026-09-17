"""Motori di ricerca agentici.

Questi motori non eseguono gli operatori dork alla lettera: interpretano la
richiesta, navigano il web e sintetizzano una risposta con le fonti. DorkLab
li integra in tre passaggi:

1. traduce la query dork in vincoli espressi in linguaggio naturale
   (:mod:`dorklab.constraints`);
2. quando possibile passa i vincoli anche in forma strutturata al motore
   (per esempio ``allowed_domains`` per la ricerca web di Claude);
3. verifica i risultati lato client e marca quelli fuori perimetro.

In questo modo la comodita' della ricerca agentica non fa perdere il controllo
sul perimetro, che in un audit difensivo e' il requisito piu' importante.
"""

from __future__ import annotations

import re
from urllib.parse import quote_plus, urlparse

from .. import constraints as constraints_mod
from .base import (BaseProvider, Credential, DORK_NONE, SearchError,
                   SearchResponse, SearchResult)
from .http import post_json

#: Numero massimo di ricerche che un motore agentico puo' innescare per query.
MAX_SEARCH_STEPS = 8


def _bget(block, key, default=""):
    """Accede a un campo sia su un oggetto dell'SDK sia su un dict (risposta HTTP)."""
    if isinstance(block, dict):
        return block.get(key, default)
    return getattr(block, key, default)


def _collect_blocks(blocks, *, results, seen, answers, provider_id, note):
    """Estrae testo e risultati di ricerca web da una lista di blocchi.

    Funziona identica sui blocchi dell'SDK (oggetti) e su quelli della risposta
    HTTP grezza (dizionari), cosi' il motore Claude non dipende dal pacchetto
    ``anthropic``.
    """
    from .base import SearchResult

    for block in blocks or []:
        block_type = _bget(block, "type")
        if block_type == "text":
            text = _bget(block, "text")
            if text:
                answers.append(text)
        elif block_type == "web_search_tool_result":
            content = _bget(block, "content", None)
            if not isinstance(content, list):
                code = _bget(content, "error_code") if content is not None else ""
                if code:
                    note("Ricerca web non riuscita: %s" % code)
                continue
            for item in content:
                url = _bget(item, "url")
                if not url or url in seen:
                    continue
                seen.add(url)
                results.append(SearchResult(
                    title=_bget(item, "title") or url, url=url, snippet="",
                    provider=provider_id, published=_bget(item, "page_age") or ""))


def _prompt_for(query: str, limit: int, translate: bool) -> str:
    """Compone il prompt da inviare a un motore agentico."""
    body = constraints_mod.to_natural_language(query) if translate else query
    return (
        "%s\n\n"
        "Restituisci fino a %d risultati pertinenti. Per ciascuno indica il "
        "titolo e l'URL diretto della risorsa. Se un vincolo non puo' essere "
        "soddisfatto dillo esplicitamente invece di restituire risultati fuori "
        "perimetro." % (body, limit)
    )


def _tavily_query(dork: str) -> str:
    """Ricava da una query dork una query di ricerca concisa per Tavily.

    Tavily si aspetta nel campo ``query`` una vera query di ricerca, non un
    blocco di istruzioni ne' gli operatori dork: quelli (``site:``) vengono
    passati separatamente come ``include_domains``. Passare l'intero dork o il
    prompt in linguaggio naturale come query produce zero risultati.
    """
    found = constraints_mod.extract(dork)
    parts: list[str] = list(found.terms)
    if found.filetypes:
        # aiuta Tavily a preferire i documenti, senza sintassi dork
        parts.append(" OR ".join(found.filetypes))
    parts.extend(found.intitle)
    parts.extend(found.inurl)
    query = " ".join(p for p in parts if p).strip()
    if not query:
        # nessun termine libero: usa il dominio come argomento, o un generico
        query = " ".join(found.sites) or "documenti pubblici"
    return query


def _allowed_domains(query: str) -> tuple[list[str], list[str]]:
    """Ricava domini ammessi ed esclusi dai vincoli site: della query.

    L'API accetta soltanto nomi host semplici: i caratteri jolly, i TLD nudi e
    i nomi a etichetta singola vengono scartati.
    """
    found = constraints_mod.extract(query)

    def clean(values: list[str]) -> list[str]:
        out: list[str] = []
        for value in values:
            host = value.strip().lstrip("*.").strip(".")
            if host.startswith("http"):
                host = urlparse(host).netloc
            host = host.split("/", 1)[0]
            if host.count(".") >= 1 and not host.startswith(".") and " " not in host:
                if host not in out:
                    out.append(host)
        return out[:64]

    return clean(found.sites), clean(found.exclude_sites)


class ClaudeAgenticProvider(BaseProvider):
    """Ricerca agentica con Claude e lo strumento di ricerca web nativo.

    Claude pianifica autonomamente piu' ricerche, segue i risultati e produce
    una sintesi con le fonti citate. E' il motore piu' adatto quando la
    domanda e' articolata ("trova tutta la documentazione tecnica su X
    pubblicata dopo il 2023 e dimmi cosa manca").
    """

    id = "claude_agentic"
    label = "Claude (ricerca agentica)"
    kind = "agentic"
    dork_support = DORK_NONE
    homepage = "https://docs.claude.com/"
    description = ("Claude esegue piu' ricerche in autonomia e sintetizza i risultati "
                   "con le fonti. I vincoli site: vengono passati come filtro di dominio. "
                   "Funziona senza installare il pacchetto 'anthropic': se non c'e', "
                   "DorkLab usa l'API via HTTP diretto.")
    credentials = [Credential("anthropic_api_key", "Chiave API Anthropic",
                              "console.anthropic.com. Puoi anche esportare ANTHROPIC_API_KEY. "
                              "Il pacchetto 'anthropic' e' facoltativo.")]

    #: Variante dello strumento con filtro dinamico dei domini.
    WEB_SEARCH_TOOL = "web_search_20260209"

    def build_url(self, query: str, results_per_page: int = 20) -> str:
        return "https://www.google.com/search?q=%s" % quote_plus(query)

    def available(self, config) -> bool:
        # Basta la chiave: se il pacchetto 'anthropic' non c'e', si usa HTTP diretto.
        return bool(config.credential("anthropic_api_key"))

    def _build_tool(self, query: str) -> dict:
        tool: dict = {"type": self.WEB_SEARCH_TOOL, "name": "web_search",
                      "max_uses": MAX_SEARCH_STEPS}
        allowed, blocked = _allowed_domains(query)
        if allowed:                     # allowed_domains e blocked si escludono
            tool["allowed_domains"] = allowed
        elif blocked:
            tool["blocked_domains"] = blocked
        return tool

    def search(self, query: str, *, config, limit: int = 20, progress=None) -> SearchResponse:
        api_key = config.credential("anthropic_api_key")
        if not api_key:
            raise SearchError("Chiave API Anthropic mancante.")

        model = config.get("claude_model") or "claude-opus-5"
        tool = self._build_tool(query)
        prompt = _prompt_for(query, limit, bool(config.get("agentic_translate", True)))

        # Si preferisce l'SDK ufficiale se installato; altrimenti HTTP diretto con
        # 'requests', gia' dipendenza di DorkLab: cosi' il motore funziona anche
        # senza il pacchetto 'anthropic'.
        try:
            import anthropic  # noqa: F401
            has_sdk = True
        except ImportError:
            has_sdk = False

        if has_sdk:
            return self._search_via_sdk(query, config=config, limit=limit,
                                        progress=progress, api_key=api_key,
                                        model=model, tool=tool, prompt=prompt)
        return self._search_via_http(query, config=config, limit=limit,
                                      progress=progress, api_key=api_key,
                                      model=model, tool=tool, prompt=prompt)

    # ------------------------------------------------------------------ SDK
    def _search_via_sdk(self, query, *, config, limit, progress, api_key,
                        model, tool, prompt) -> SearchResponse:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        messages: list[dict] = [{"role": "user", "content": prompt}]
        answers: list[str] = []
        results: list[SearchResult] = []
        seen: set[str] = set()
        restarts = 0
        response = None

        while True:
            self._note(progress, "Claude: ricerca in corso%s" %
                       (" (ripresa %d)" % restarts if restarts else ""))
            try:
                with client.beta.messages.stream(
                    model=model, max_tokens=16000,
                    thinking={"type": "adaptive"},
                    betas=["server-side-fallback-2026-06-01"],
                    fallbacks=[{"model": "claude-opus-4-8"}],
                    tools=[tool], messages=messages,
                ) as stream:
                    response = stream.get_final_message()
            except anthropic.APIStatusError as exc:
                raise SearchError("Claude ha risposto con un errore: %s" % exc) from exc
            except Exception as exc:  # pragma: no cover - rete
                raise SearchError("Chiamata a Claude fallita: %s" % exc) from exc

            if response.stop_reason == "refusal":
                detail = getattr(getattr(response, "stop_details", None), "explanation", "")
                raise SearchError(
                    "La richiesta e' stata declinata dai filtri del modello. %s" % (detail or ""))

            _collect_blocks(response.content, results=results, seen=seen, answers=answers,
                            provider_id=self.id,
                            note=lambda m: self._note(progress, m))

            if response.stop_reason != "pause_turn":
                break
            restarts += 1
            if restarts > 4:
                break
            messages = [{"role": "user", "content": prompt},
                        {"role": "assistant", "content": response.content}]

        return SearchResponse(
            provider=self.id, query=query, results=results[:limit],
            answer="\n\n".join(answers).strip(),
            meta={"modello": getattr(response, "model", model),
                  "ricerche": len(results), "via": "SDK anthropic"})

    # ------------------------------------------------------------ HTTP diretto
    def _search_via_http(self, query, *, config, limit, progress, api_key,
                         model, tool, prompt) -> SearchResponse:
        """Interroga l'API Messages via HTTP, senza il pacchetto 'anthropic'.

        Richiesta minimale (nessun header beta) per massimizzare la compatibilita':
        modello, ricerca web nativa, pensiero adattivo. Il rifiuto di policy viene
        segnalato con un errore chiaro invece che con un fallback lato server.
        """
        from .http import post_json

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        endpoint = "https://api.anthropic.com/v1/messages"
        messages: list[dict] = [{"role": "user", "content": prompt}]
        answers: list[str] = []
        results: list[SearchResult] = []
        seen: set[str] = set()
        restarts = 0
        payload: dict = {}

        while True:
            self._note(progress, "Claude (HTTP): ricerca in corso%s" %
                       (" (ripresa %d)" % restarts if restarts else ""))
            body = {
                "model": model, "max_tokens": 16000,
                "thinking": {"type": "adaptive"},
                "tools": [tool], "messages": messages,
            }
            payload = post_json(endpoint, json=body, headers=headers, timeout=180)

            if payload.get("stop_reason") == "refusal":
                detail = (payload.get("stop_details") or {}).get("explanation", "")
                raise SearchError(
                    "La richiesta e' stata declinata dai filtri del modello. %s" % (detail or ""))

            _collect_blocks(payload.get("content"), results=results, seen=seen,
                            answers=answers, provider_id=self.id,
                            note=lambda m: self._note(progress, m))

            if payload.get("stop_reason") != "pause_turn":
                break
            restarts += 1
            if restarts > 4:
                break
            messages = [{"role": "user", "content": prompt},
                        {"role": "assistant", "content": payload.get("content")}]

        return SearchResponse(
            provider=self.id, query=query, results=results[:limit],
            answer="\n\n".join(answers).strip(),
            meta={"modello": payload.get("model", model),
                  "ricerche": len(results), "via": "HTTP diretto"})

class PerplexityProvider(BaseProvider):
    """Perplexity Sonar: risposta sintetica con citazioni."""

    id = "perplexity"
    label = "Perplexity (agentico)"
    kind = "agentic"
    dork_support = DORK_NONE
    homepage = "https://docs.perplexity.ai/"
    description = "Risposta sintetica con fonti. Buono per domande esplorative."
    credentials = [Credential("perplexity_api_key", "Chiave API Perplexity",
                              "Impostazioni account Perplexity, sezione API.")]
    ENDPOINT = "https://api.perplexity.ai/chat/completions"

    def build_url(self, query: str, results_per_page: int = 20) -> str:
        return "https://www.perplexity.ai/search?q=%s" % quote_plus(query)

    def search(self, query: str, *, config, limit: int = 20, progress=None) -> SearchResponse:
        key = config.credential("perplexity_api_key")
        if not key:
            raise SearchError("Chiave API Perplexity mancante.")

        self._note(progress, "Perplexity: interrogazione in corso")
        payload = post_json(
            self.ENDPOINT,
            headers={"Authorization": "Bearer %s" % key},
            json={
                "model": config.get("perplexity_model") or "sonar-pro",
                "messages": [{"role": "user",
                              "content": _prompt_for(query, limit,
                                                     bool(config.get("agentic_translate", True)))}],
            },
            timeout=90,
        )

        choices = payload.get("choices") or []
        answer = ""
        if choices:
            answer = ((choices[0].get("message") or {}).get("content") or "").strip()

        results: list[SearchResult] = []
        for item in payload.get("search_results") or []:
            results.append(SearchResult(
                title=item.get("title", "") or item.get("url", ""),
                url=item.get("url", ""),
                snippet=item.get("snippet", "") or "",
                provider=self.id,
                published=item.get("date", "") or "",
                raw=item,
            ))
        if not results:
            for url in payload.get("citations") or []:
                results.append(SearchResult(title=url, url=url, provider=self.id))

        return SearchResponse(provider=self.id, query=query, answer=answer,
                              results=results[:limit],
                              meta={"modello": payload.get("model", "")})


class TavilyProvider(BaseProvider):
    """Tavily: API di ricerca pensata per agenti.

    DorkLab usa Tavily sempre alla massima profondita' disponibile:

    * ``search_depth="advanced"`` - il livello piu' approfondito previsto
      dall'API, con reranking dei contenuti;
    * ``chunks_per_source=3`` - il massimo di frammenti estratti per fonte,
      accettato solo in modalita' advanced;
    * ``include_answer="advanced"`` - sintesi estesa invece di quella breve;
    * ``include_raw_content=True`` - testo completo della pagina, che alimenta
      l'estrazione documentale e la ricerca nei contenuti.

    Poiche' una singola chiamata restituisce al massimo 20 risultati, quando si
    chiede di piu' DorkLab scompone la query dork in varianti (una per
    estensione, una per dominio) e ne unisce i risultati deduplicati: e' il
    modo per andare oltre il tetto per chiamata senza forzare l'API.
    """

    id = "tavily"
    label = "Tavily (agentico, profondita' massima)"
    kind = "agentic"
    dork_support = DORK_NONE
    homepage = "https://tavily.com/"
    description = ("Ricerca avanzata per agenti, sempre in modalita' advanced. "
                   "Include l'estrazione del contenuto completo delle pagine.")
    credentials = [Credential("tavily_api_key", "Chiave API Tavily",
                              "app.tavily.com - oppure esporta TAVILY_API_KEY.")]
    ENDPOINT = "https://api.tavily.com/search"
    EXTRACT_ENDPOINT = "https://api.tavily.com/extract"
    #: Tetto di risultati per singola chiamata imposto dall'API.
    PER_CALL = 20
    #: Numero massimo di varianti generate in modalita' approfondita.
    MAX_VARIANTS = 6

    def build_url(self, query: str, results_per_page: int = 20) -> str:
        return "https://www.google.com/search?q=%s" % quote_plus(query)

    # ------------------------------------------------------------- profondita'
    def _variants(self, query: str, limit: int) -> list[str]:
        """Scompone la query in varianti per superare il tetto per chiamata.

        Una query come ``site:x.it (filetype:pdf OR filetype:docx)`` diventa
        due ricerche distinte, una per estensione: ciascuna riceve il proprio
        budget di 20 risultati invece di spartirsene uno solo.
        """
        if limit <= self.PER_CALL:
            return [query]

        found = constraints_mod.extract(query)
        variants: list[str] = []

        if len(found.filetypes) > 1:
            for extension in found.filetypes[: self.MAX_VARIANTS]:
                rebuilt = re.sub(r"\(?\s*(?:-?(?:filetype|ext|mime):\S+\s*(?:OR\s*)?)+\)?",
                                 "filetype:%s " % extension, query, count=1)
                variants.append(" ".join(rebuilt.split()))
        elif len(found.sites) > 1:
            for site in found.sites[: self.MAX_VARIANTS]:
                rebuilt = re.sub(r"\(?\s*(?:-?site:\S+\s*(?:OR\s*)?)+\)?",
                                 "site:%s " % site, query, count=1)
                variants.append(" ".join(rebuilt.split()))

        if not variants:
            return [query]
        # la query originale resta come prima variante: e' quella piu' fedele
        return [query, *[v for v in variants if v != query]][: self.MAX_VARIANTS + 1]

    def _call(self, query: str, *, key: str, config, limit: int,
              allowed: list[str], blocked: list[str]) -> dict:
        body: dict = {
            # compatibilita': alcune chiavi Tavily accettano l'auth nel corpo
            "api_key": key,
            "query": query,
            "max_results": max(1, min(limit, self.PER_CALL)),
            "search_depth": "advanced",   # massima profondita' disponibile
            "chunks_per_source": 3,       # ammesso solo con search_depth advanced
            "include_answer": "advanced",
            "include_raw_content": True,
            "topic": "general",
        }
        if allowed:
            body["include_domains"] = allowed
        if blocked:
            body["exclude_domains"] = blocked
        return post_json(self.ENDPOINT,
                         headers={"Authorization": "Bearer %s" % key},
                         json=body, timeout=120)

    def search(self, query: str, *, config, limit: int = 20, progress=None) -> SearchResponse:
        key = config.credential("tavily_api_key")
        if not key:
            raise SearchError("Chiave API Tavily mancante.")

        allowed, blocked = _allowed_domains(query)
        deep = bool(config.get("tavily_deep", True))

        queries = self._variants(query, limit) if deep else [query]
        results: list[SearchResult] = []
        answers: list[str] = []
        seen: set[str] = set()
        budget = limit

        for index, variant in enumerate(queries, start=1):
            if budget <= 0:
                break
            # ogni variante conserva il proprio site:, quindi i domini ammessi
            # vanno ricalcolati per variante (una sola per volta in profondita')
            variant_allowed, variant_blocked = _allowed_domains(variant)
            search_query = _tavily_query(variant)
            self._note(progress, "Tavily (advanced) %d/%d: %s"
                       % (index, len(queries), search_query[:60] or variant[:60]))
            payload = self._call(search_query, key=key, config=config,
                                 limit=min(budget, self.PER_CALL),
                                 allowed=variant_allowed or allowed,
                                 blocked=variant_blocked or blocked)

            answer = (payload.get("answer") or "").strip()
            if answer and answer not in answers:
                answers.append(answer)

            for item in payload.get("results") or []:
                url = item.get("url", "")
                normalized = url.rstrip("/").lower()
                if not url or normalized in seen:
                    continue
                seen.add(normalized)
                raw_text = item.get("raw_content") or ""
                results.append(SearchResult(
                    title=item.get("title", "") or url,
                    url=url,
                    snippet=" ".join((item.get("content") or "").split())[:400],
                    provider=self.id,
                    score=float(item.get("score") or 0),
                    published=item.get("published_date", "") or "",
                    raw={**item, "raw_content_len": len(raw_text)},
                ))
                budget -= 1

        results.sort(key=lambda r: r.score, reverse=True)
        return SearchResponse(
            provider=self.id, query=query, answer="\n\n".join(answers),
            results=results[:limit],
            meta={"profondita'": "advanced", "varianti eseguite": len(queries),
                  "frammenti per fonte": 3},
        )

    # -------------------------------------------------------------- estrazione
    def extract_content(self, urls: list[str], *, config, progress=None) -> dict[str, str]:
        """Estrae il contenuto testuale completo delle pagine indicate.

        Usa l'endpoint ``/extract`` con ``extract_depth="advanced"``: e' il
        modo piu' affidabile per recuperare il testo di un documento anche
        quando la pagina e' costruita lato client.
        """
        key = config.credential("tavily_api_key")
        if not key:
            raise SearchError("Chiave API Tavily mancante.")

        extracted: dict[str, str] = {}
        # l'endpoint accetta piu' URL per chiamata: si procede a blocchi
        for start in range(0, len(urls), 20):
            batch = urls[start:start + 20]
            self._note(progress, "Tavily extract: %d URL" % len(batch))
            payload = post_json(
                self.EXTRACT_ENDPOINT,
                headers={"Authorization": "Bearer %s" % key},
                json={"urls": batch, "extract_depth": "advanced",
                      "include_images": False},
                timeout=180,
            )
            for item in payload.get("results") or []:
                url = item.get("url", "")
                if url:
                    extracted[url] = item.get("raw_content") or ""
            for item in payload.get("failed_results") or []:
                url = item.get("url", "")
                if url:
                    extracted.setdefault(url, "")
        return extracted


class ExaProvider(BaseProvider):
    """Exa: ricerca semantica/neurale, utile quando le parole chiave non bastano."""

    id = "exa"
    label = "Exa (semantico)"
    kind = "agentic"
    dork_support = DORK_NONE
    homepage = "https://exa.ai/"
    description = ("Ricerca per significato invece che per parole chiave: trova documenti "
                   "simili a una descrizione anche senza corrispondenza testuale.")
    credentials = [Credential("exa_api_key", "Chiave API Exa", "dashboard.exa.ai")]
    ENDPOINT = "https://api.exa.ai/search"

    def build_url(self, query: str, results_per_page: int = 20) -> str:
        return "https://exa.ai/search?q=%s" % quote_plus(query)

    def search(self, query: str, *, config, limit: int = 20, progress=None) -> SearchResponse:
        key = config.credential("exa_api_key")
        if not key:
            raise SearchError("Chiave API Exa mancante.")

        found = constraints_mod.extract(query)
        allowed, blocked = _allowed_domains(query)
        body: dict = {
            "query": constraints_mod.to_natural_language(query)
            if config.get("agentic_translate", True) else query,
            "numResults": min(limit, 25),
            "type": "auto",
            "contents": {"text": {"maxCharacters": 400}},
        }
        if allowed:
            body["includeDomains"] = allowed
        if blocked:
            body["excludeDomains"] = blocked

        self._note(progress, "Exa: interrogazione in corso")
        payload = post_json(self.ENDPOINT,
                            headers={"x-api-key": key},
                            json=body, timeout=60)

        results = []
        for item in payload.get("results") or []:
            text = item.get("text") or ""
            results.append(SearchResult(
                title=item.get("title", "") or item.get("url", ""),
                url=item.get("url", ""),
                snippet=" ".join(text.split())[:300],
                provider=self.id,
                published=item.get("publishedDate", "") or "",
                score=float(item.get("score") or 0),
                raw=item,
            ))
        return SearchResponse(provider=self.id, query=query, results=results[:limit])


def agentic_providers() -> list[BaseProvider]:
    return [ClaudeAgenticProvider(), PerplexityProvider(), TavilyProvider(), ExaProvider()]
