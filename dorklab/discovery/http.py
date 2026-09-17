"""Sessione HTTP condivisa dalle fonti di scoperta."""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - dipende dall'ambiente
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from .base import DiscoveryError

DEFAULT_TIMEOUT = 30


def _require() -> None:
    if requests is None:
        raise DiscoveryError(
            "Il pacchetto 'requests' non e' installato. "
            "Su Fedora: sudo dnf install python3-requests"
        )


def session(user_agent: str):
    _require()
    handle = requests.Session()
    handle.headers.update({"User-Agent": user_agent})
    return handle


def get(url: str, *, user_agent: str, params: dict | None = None,
        timeout: int = DEFAULT_TIMEOUT, handle=None, stream: bool = False):
    _require()
    caller = handle or requests
    try:
        response = caller.get(url, params=params, timeout=timeout, stream=stream,
                              headers=None if handle else {"User-Agent": user_agent})
    except Exception as exc:  # pragma: no cover - rete
        raise DiscoveryError("Connessione fallita: %s" % exc) from exc
    return response


def get_json(url: str, *, user_agent: str, params: dict | None = None,
             timeout: int = DEFAULT_TIMEOUT, handle=None) -> Any:
    response = get(url, user_agent=user_agent, params=params, timeout=timeout, handle=handle)
    if response.status_code == 429:
        raise DiscoveryError("Troppe richieste (429): attendi prima di riprovare.")
    if response.status_code >= 400:
        raise DiscoveryError("Errore HTTP %s da %s" % (response.status_code, url))
    try:
        return response.json()
    except ValueError as exc:
        raise DiscoveryError("Risposta non in formato JSON da %s" % url) from exc


def get_text(url: str, *, user_agent: str, timeout: int = DEFAULT_TIMEOUT,
             handle=None, max_bytes: int = 8_000_000) -> tuple[int, bytes]:
    """Scarica il corpo di una risposta con un tetto di dimensione."""
    response = get(url, user_agent=user_agent, timeout=timeout, handle=handle, stream=True)
    status = response.status_code
    chunks: list[bytes] = []
    read = 0
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        read += len(chunk)
        if read > max_bytes:
            break
        chunks.append(chunk)
    response.close()
    return status, b"".join(chunks)
