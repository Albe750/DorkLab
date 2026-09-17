"""Registro dei motori di ricerca disponibili."""

from __future__ import annotations

from .. import constraints as constraints_mod
from .agentic import agentic_providers
from .api_engines import api_providers
from .base import (BaseProvider, Credential, DORK_FULL, DORK_HELP, DORK_LABELS,
                   DORK_NONE, DORK_PARTIAL, KIND_LABELS, SearchError,
                   SearchResponse, SearchResult)
from .browser import browser_providers

_REGISTRY: dict[str, BaseProvider] = {}


def _build() -> dict[str, BaseProvider]:
    if not _REGISTRY:
        for provider in [*browser_providers(), *api_providers(), *agentic_providers()]:
            _REGISTRY[provider.id] = provider
    return _REGISTRY


def all_providers() -> list[BaseProvider]:
    return list(_build().values())


def get(provider_id: str) -> BaseProvider | None:
    return _build().get(provider_id)


def by_kind(kind: str) -> list[BaseProvider]:
    return [p for p in all_providers() if p.kind == kind]


def kinds() -> list[str]:
    return ["browser", "api", "agentic"]


def default_provider() -> BaseProvider:
    return _build()["google_browser"]


def annotate(response: SearchResponse) -> SearchResponse:
    """Verifica i risultati contro i vincoli espressi nella query.

    Ogni risultato riceve l'esito della verifica e un giudizio complessivo
    (`ok`, `parziale`, `fuori`, `sconosciuto`). Per i motori agentici, che non
    eseguono gli operatori alla lettera, e' l'unico modo per sapere se il
    perimetro richiesto e' stato davvero rispettato.
    """
    found = constraints_mod.extract(response.query)
    if found.is_empty():
        return response
    for result in response.results:
        if not result.filetype:
            result.filetype = constraints_mod.guess_filetype(result.url, result.mime)
        result.checks = constraints_mod.verify(found, result.url, result.title, result.mime)
        result.compliance = constraints_mod.compliance(result.checks)
    return response


def dedupe(responses: list[SearchResponse]) -> list[SearchResult]:
    """Unisce piu' risposte eliminando gli URL duplicati."""
    seen: set[str] = set()
    merged: list[SearchResult] = []
    for response in responses:
        for result in response.results:
            key = result.url.rstrip("/").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(result)
    return merged


__all__ = [
    "all_providers", "get", "by_kind", "kinds", "default_provider", "annotate",
    "dedupe", "BaseProvider", "Credential", "SearchError", "SearchResponse",
    "SearchResult", "DORK_FULL", "DORK_PARTIAL", "DORK_NONE", "DORK_LABELS",
    "DORK_HELP",
    "KIND_LABELS",
]
