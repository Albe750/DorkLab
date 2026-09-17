"""Helper HTTP condiviso dai motori che espongono un'API."""

from __future__ import annotations

from typing import Any

try:  # pragma: no cover - dipende dall'ambiente
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

from .base import SearchError

DEFAULT_TIMEOUT = 25


def _require_requests() -> None:
    if requests is None:
        raise SearchError(
            "Il pacchetto 'requests' non e' installato. "
            "Su Fedora: sudo dnf install python3-requests"
        )


def get_json(url: str, *, params: dict | None = None, headers: dict | None = None,
             timeout: int = DEFAULT_TIMEOUT) -> Any:
    _require_requests()
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
    except Exception as exc:  # pragma: no cover - rete
        raise SearchError("Connessione fallita: %s" % exc) from exc
    return _handle(response)


def post_json(url: str, *, json: dict | None = None, headers: dict | None = None,
              timeout: int = DEFAULT_TIMEOUT) -> Any:
    _require_requests()
    try:
        response = requests.post(url, json=json, headers=headers, timeout=timeout)
    except Exception as exc:  # pragma: no cover - rete
        raise SearchError("Connessione fallita: %s" % exc) from exc
    return _handle(response)


def _handle(response) -> Any:
    if response.status_code == 401:
        raise SearchError("Credenziale rifiutata (401): controlla la chiave API.")
    if response.status_code == 403:
        raise SearchError("Accesso negato (403): chiave non valida o quota esaurita.")
    if response.status_code == 429:
        raise SearchError("Troppe richieste (429): attendi prima di riprovare.")
    if response.status_code >= 400:
        detail = ""
        try:
            payload = response.json()
            detail = str(payload.get("error") or payload.get("message") or "")[:300]
        except Exception:  # noqa: BLE001 - il corpo puo' non essere JSON
            detail = response.text[:300]
        raise SearchError("Errore HTTP %s: %s" % (response.status_code, detail))
    try:
        return response.json()
    except ValueError as exc:
        raise SearchError("Risposta non in formato JSON.") from exc
