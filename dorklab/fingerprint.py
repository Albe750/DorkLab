"""Riconoscimento della tecnologia di un sito e dork suggeriti.

Dai URL scoperti (estensioni, percorsi tipici), dalle intestazioni HTTP e dai
cookie si deduce lo stack del sito - ASP.NET, PHP, WordPress, Java, ecc. Ogni
tecnologia porta con se' i dork piu' adatti a cercarne le esposizioni tipiche,
cosi' non si parte da zero: il sito stesso suggerisce dove guardare.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlparse

from .audit import normalize_domain
from .paths import DATA_DIR


@lru_cache(maxsize=1)
def _catalog() -> dict:
    with (DATA_DIR / "fingerprints.json").open(encoding="utf-8") as handle:
        return json.load(handle)


@dataclass
class Match:
    tech_id: str
    label: str
    color: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class Dork:
    label: str
    query: str
    tech: str = ""


@dataclass
class FingerprintReport:
    domain: str
    matches: list[Match] = field(default_factory=list)
    headers: dict = field(default_factory=dict)

    @property
    def found(self) -> bool:
        return bool(self.matches)

    def dorks(self) -> list[Dork]:
        return suggested_dorks([m.tech_id for m in self.matches], self.domain)


def _tech(tech_id: str) -> dict | None:
    for tech in _catalog()["technologies"]:
        if tech["id"] == tech_id:
            return tech
    return None


def detect_from_urls(urls: list[str]) -> dict[str, list[str]]:
    """Rileva tecnologie dai marcatori presenti negli URL."""
    blob = " ".join(u.lower() for u in urls)
    found: dict[str, list[str]] = {}
    for tech in _catalog()["technologies"]:
        hits = [marker for marker in tech.get("url_markers", []) if marker in blob]
        if hits:
            found[tech["id"]] = ["URL: %s" % h for h in hits[:4]]
    return found


def detect_from_headers(headers: dict) -> dict[str, list[str]]:
    """Rileva tecnologie da Server, X-Powered-By, X-Generator e cookie."""
    if not headers:
        return {}
    lower = {k.lower(): str(v).lower() for k, v in headers.items()}
    server = lower.get("server", "")
    powered = lower.get("x-powered-by", "")
    generator = lower.get("x-generator", "")
    cookies = lower.get("set-cookie", "")

    found: dict[str, list[str]] = {}
    for tech in _catalog()["technologies"]:
        evidence: list[str] = []
        for needle in tech.get("header_server", []):
            if needle in server:
                evidence.append("Server: %s" % needle)
        for needle in tech.get("header_powered", []):
            if needle in powered:
                evidence.append("X-Powered-By: %s" % needle)
        for needle in tech.get("header_extra", []):
            if needle in lower:
                evidence.append("intestazione: %s" % needle)
        for needle in tech.get("generator", []):
            if needle in generator:
                evidence.append("X-Generator: %s" % needle)
        for needle in tech.get("cookies", []):
            if needle in cookies:
                evidence.append("cookie: %s" % needle)
        if evidence:
            found[tech["id"]] = evidence
    return found


def probe_headers(domain: str, config) -> dict:
    """Una sola richiesta alla home per leggere le intestazioni del server."""
    from .discovery.http import get

    domain = normalize_domain(domain)
    for base in ("https://%s/" % domain, "https://www.%s/" % domain):
        try:
            response = get(base, user_agent=config.get("user_agent"),
                           timeout=15, stream=True, allow_redirects=True)
            headers = dict(response.headers)
            response.close()
            return headers
        except Exception:  # noqa: BLE001 - best effort
            continue
    return {}


def analyze(domain: str, urls: list[str], config, *, probe: bool = True) -> FingerprintReport:
    """Analizza dominio e URL scoperti, restituendo tecnologie ed evidenze."""
    domain = normalize_domain(domain)
    evidence: dict[str, list[str]] = {}

    for tech_id, hits in detect_from_urls(urls).items():
        evidence.setdefault(tech_id, []).extend(hits)

    headers: dict = {}
    if probe:
        headers = probe_headers(domain, config)
        for tech_id, hits in detect_from_headers(headers).items():
            evidence.setdefault(tech_id, []).extend(hits)

    matches = []
    for tech in _catalog()["technologies"]:
        if tech["id"] in evidence:
            matches.append(Match(tech["id"], tech["label"], tech.get("color", "#6b7280"),
                                 evidence[tech["id"]]))
    return FingerprintReport(domain=domain, matches=matches, headers=headers)


def suggested_dorks(tech_ids: list[str], domain: str) -> list[Dork]:
    """Dork adatti alle tecnologie rilevate, piu' un nucleo sempre utile."""
    domain = normalize_domain(domain)
    dorks: list[Dork] = []
    seen: set[str] = set()

    def add(label: str, template: str, tech: str) -> None:
        query = template.replace("{domain}", domain)
        if query not in seen:
            seen.add(query)
            dorks.append(Dork(label=label, query=query, tech=tech))

    for tech_id in tech_ids:
        tech = _tech(tech_id)
        if not tech:
            continue
        for item in tech.get("dorks", []):
            add(item["label"], item["template"], tech["label"])

    for item in _catalog().get("always", []):
        add(item["label"], item["template"], "generico")
    return dorks
