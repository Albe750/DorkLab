"""Download controllato dei documenti trovati.

Il download e' volutamente conservativo: un ritardo fra le richieste, il
rispetto di robots.txt, un tetto alla dimensione dei file e un User-Agent
identificabile. Scaricare documenti pubblici e' legittimo; farlo in modo
aggressivo non lo e' e porta solo a farsi bloccare.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, unquote
from urllib.robotparser import RobotFileParser

try:  # pragma: no cover - dipende dall'ambiente
    import requests
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class DownloadOutcome:
    url: str
    path: str = ""
    ok: bool = False
    reason: str = ""
    size: int = 0


def safe_filename(url: str, fallback: str = "documento") -> str:
    """Ricava un nome file prevedibile e sicuro dall'URL."""
    name = unquote(Path(urlparse(url).path).name) or fallback
    name = _UNSAFE.sub("_", name).strip("._") or fallback
    if len(name) > 120:
        stem, dot, ext = name.rpartition(".")
        name = (stem[:100] + dot + ext) if dot else name[:120]
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    stem, dot, ext = name.rpartition(".")
    if dot:
        return "%s_%s.%s" % (stem, digest, ext)
    return "%s_%s" % (name, digest)


class RobotsCache:
    """Cache dei robots.txt per host, per non riscaricarli a ogni file."""

    def __init__(self, user_agent: str) -> None:
        self.user_agent = user_agent
        self._cache: dict[str, RobotFileParser | None] = {}

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = "%s://%s" % (parsed.scheme, parsed.netloc)
        if origin not in self._cache:
            parser = RobotFileParser()
            parser.set_url(origin + "/robots.txt")
            try:
                parser.read()
            except Exception:  # noqa: BLE001 - robots assente o irraggiungibile
                parser = None  # type: ignore[assignment]
            self._cache[origin] = parser
        parser = self._cache[origin]
        if parser is None:
            return True  # nessun robots.txt leggibile: si procede
        try:
            return parser.can_fetch(self.user_agent, url)
        except Exception:  # noqa: BLE001
            return True


class Downloader:
    """Scarica una lista di URL in una cartella, con controlli di sicurezza."""

    def __init__(self, directory: str, *, user_agent: str, delay: float = 1.5,
                 respect_robots: bool = True, max_mb: int = 50,
                 jitter: float = 0.0) -> None:
        self.directory = Path(directory)
        self.user_agent = user_agent
        self.delay = max(0.0, float(delay))
        self.jitter = max(0.0, min(1.0, float(jitter)))
        self.respect_robots = respect_robots
        self.max_bytes = max(1, int(max_mb)) * 1024 * 1024
        self._robots = RobotsCache(user_agent)
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def fetch(self, url: str) -> DownloadOutcome:
        if requests is None:
            return DownloadOutcome(url, reason="Pacchetto 'requests' non installato")
        if not url.lower().startswith(("http://", "https://")):
            return DownloadOutcome(url, reason="Schema URL non supportato")
        if self.respect_robots and not self._robots.allowed(url):
            return DownloadOutcome(url, reason="Bloccato da robots.txt")

        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / safe_filename(url)
        if target.exists():
            return DownloadOutcome(url, path=str(target), ok=True,
                                   reason="Gia' presente", size=target.stat().st_size)

        try:
            with requests.get(url, stream=True, timeout=30,
                              headers={"User-Agent": self.user_agent}) as response:
                if response.status_code >= 400:
                    return DownloadOutcome(url, reason="HTTP %s" % response.status_code)

                declared = int(response.headers.get("Content-Length") or 0)
                if declared and declared > self.max_bytes:
                    return DownloadOutcome(
                        url, reason="File troppo grande (%.1f MB)" % (declared / 1024 / 1024))

                written = 0
                tmp = target.with_suffix(target.suffix + ".part")
                with tmp.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=65536):
                        if self.cancelled:
                            handle.close()
                            tmp.unlink(missing_ok=True)
                            return DownloadOutcome(url, reason="Annullato")
                        if not chunk:
                            continue
                        written += len(chunk)
                        if written > self.max_bytes:
                            handle.close()
                            tmp.unlink(missing_ok=True)
                            return DownloadOutcome(url, reason="Superato il limite di dimensione")
                        handle.write(chunk)
                os.replace(tmp, target)
        except Exception as exc:  # noqa: BLE001 - rete
            return DownloadOutcome(url, reason=str(exc)[:200])

        return DownloadOutcome(url, path=str(target), ok=True, size=written)

    def _pause(self) -> float:
        """Ritardo fra i download, con variazione casuale se attiva."""
        if self.jitter <= 0:
            return self.delay
        import random

        return max(0.0, self.delay * (1.0 + random.uniform(-self.jitter, self.jitter)))

    def fetch_all(self, urls: list[str], progress=None) -> list[DownloadOutcome]:
        outcomes: list[DownloadOutcome] = []
        total = len(urls)
        for index, url in enumerate(urls, start=1):
            if self.cancelled:
                break
            if progress:
                progress(index, total, url)
            outcomes.append(self.fetch(url))
            if self.delay and index < total:
                time.sleep(self._pause())
        return outcomes
