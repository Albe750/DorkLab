"""Configurazione persistente dell'applicazione."""

from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

from .paths import config_dir, default_download_dir

CONFIG_FILE = "config.json"

DEFAULTS: dict[str, Any] = {
    "provider": "tavily",
    "results_per_page": 10,
    "max_results": 60,
    "tavily_deep": True,
    "theme": "auto",
    "request_delay": 1.5,
    "respect_robots": True,
    "max_download_mb": 50,
    "download_dir": "",
    "user_agent": "DorkLab/1.0 (ricerca documentale; +https://github.com/Albe750/DorkLab)",
    "confirm_before_browser_batch": True,
    "agentic_translate": True,
    "agentic_filter": False,
    "credentials": {},
    "searxng_url": "",
    "claude_model": "claude-opus-5",
    "perplexity_model": "sonar-pro",
    "audit_authorized_domains": [],
    "window": {},
}

#: Le credenziali possono anche arrivare dall'ambiente, cosi' da non doverle
#: scrivere su disco.
ENV_KEYS = {
    "google_api_key": "DORKLAB_GOOGLE_API_KEY",
    "google_cx": "DORKLAB_GOOGLE_CX",
    "brave_api_key": "BRAVE_SEARCH_API_KEY",
    "serpapi_key": "SERPAPI_API_KEY",
    "tavily_api_key": "TAVILY_API_KEY",
    "exa_api_key": "EXA_API_KEY",
    "perplexity_api_key": "PERPLEXITY_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
}


class Config:
    """Wrapper leggero su un dizionario salvato in ~/.config/dorklab."""

    def __init__(self, values: dict[str, Any] | None = None) -> None:
        self._values = deepcopy(DEFAULTS)
        if values:
            self._values.update(values)
            # merge non distruttivo dei sottodizionari
            for key in ("credentials", "window"):
                merged = deepcopy(DEFAULTS[key])
                merged.update(values.get(key) or {})
                self._values[key] = merged

    # ----------------------------------------------------------------- accesso
    def __getitem__(self, key: str) -> Any:
        return self._values.get(key, DEFAULTS.get(key))

    def __setitem__(self, key: str, value: Any) -> None:
        self._values[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default if default is not None else DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value

    def as_dict(self) -> dict[str, Any]:
        return deepcopy(self._values)

    # ------------------------------------------------------------- credenziali
    def credential(self, name: str) -> str:
        """Legge una credenziale: prima l'ambiente, poi il file di configurazione."""
        env_var = ENV_KEYS.get(name)
        if env_var:
            value = os.environ.get(env_var)
            if value:
                return value.strip()
        return str(self._values.get("credentials", {}).get(name, "")).strip()

    def set_credential(self, name: str, value: str) -> None:
        self._values.setdefault("credentials", {})[name] = value.strip()

    def credential_source(self, name: str) -> str:
        env_var = ENV_KEYS.get(name)
        if env_var and os.environ.get(env_var):
            return "ambiente (%s)" % env_var
        if self._values.get("credentials", {}).get(name):
            return "file di configurazione"
        return "non impostata"

    # ------------------------------------------------------------------ cartelle
    def number(self, key: str, default: float) -> float:
        """Legge un valore numerico rispettando lo zero.

        Serve a non trasformare uno 0 legittimo nel valore predefinito, come
        farebbe il pattern `config.get(key) or default`.
        """
        value = self._values.get(key, default)
        if value is None:
            return float(default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    def download_path(self) -> str:
        value = str(self._values.get("download_dir") or "").strip()
        return value or str(default_download_dir())

    # -------------------------------------------------------------- persistenza
    @classmethod
    def load(cls) -> "Config":
        path = config_dir() / CONFIG_FILE
        if not path.exists():
            return cls()
        try:
            with path.open(encoding="utf-8") as handle:
                return cls(json.load(handle))
        except (OSError, json.JSONDecodeError):
            return cls()

    def save(self) -> None:
        directory = config_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / CONFIG_FILE
        tmp = path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as handle:
            json.dump(self._values, handle, indent=2, ensure_ascii=False)
        tmp.replace(path)
        try:
            # le credenziali sono in chiaro: almeno restringiamo i permessi
            path.chmod(0o600)
        except OSError:
            pass
