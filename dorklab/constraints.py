"""Estrazione e verifica dei vincoli espressi in una query.

Serve a due cose:

1. I motori "agentici" (Claude, Perplexity, Tavily, Exa) interpretano la
   richiesta invece di eseguire letteralmente gli operatori. DorkLab estrae i
   vincoli dalla query, li traduce in linguaggio naturale per il motore e poi
   verifica lato client quali risultati li rispettano davvero.
2. Anche con i motori tradizionali la verifica evidenzia i risultati fuori
   perimetro, utile soprattutto durante un audit su un dominio specifico.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .query import PREFIX_OPERATORS

_TOKEN_RE = re.compile(r'(-?)([A-Za-z_]+):("[^"]*"|\S+)')


@dataclass
class Constraints:
    """Vincoli verificabili lato client estratti da una query."""

    sites: list[str] = field(default_factory=list)
    exclude_sites: list[str] = field(default_factory=list)
    filetypes: list[str] = field(default_factory=list)
    inurl: list[str] = field(default_factory=list)
    exclude_inurl: list[str] = field(default_factory=list)
    intitle: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any((self.sites, self.exclude_sites, self.filetypes,
                        self.inurl, self.exclude_inurl, self.intitle))


def extract(query: str) -> Constraints:
    """Legge una query testuale e ne ricava i vincoli verificabili."""
    constraints = Constraints()

    for negated, operator, value in _TOKEN_RE.findall(query):
        operator = operator.lower()
        if operator not in PREFIX_OPERATORS:
            continue
        # le parentesi di raggruppamento restano attaccate al valore:
        # `(filetype:pdf OR filetype:docx)` -> il secondo valore e' "docx)"
        value = value.strip('"').strip().strip("()").strip().lower()
        if not value:
            continue
        negative = negated == "-"

        if operator in {"site", "domain", "host"}:
            (constraints.exclude_sites if negative else constraints.sites).append(value)
        elif operator in {"filetype", "ext", "mime"}:
            (constraints.filetypes if not negative else []).append(value)
        elif operator in {"inurl", "allinurl", "url"}:
            (constraints.exclude_inurl if negative else constraints.inurl).append(value)
        elif operator in {"intitle", "allintitle", "title"}:
            if not negative:
                constraints.intitle.append(value)

    residual = _TOKEN_RE.sub(" ", query)
    for word in re.findall(r'"[^"]+"|\S+', residual):
        word = word.strip()
        if not word or word.upper() in {"OR", "AND"}:
            continue
        if word.startswith("-"):
            continue
        cleaned = word.strip('()"').strip()
        if cleaned and not cleaned.startswith("*"):
            constraints.terms.append(cleaned.lower())

    return constraints


def _host_matches(host: str, pattern: str) -> bool:
    """Confronta un host con un pattern di site:, gestendo il jolly iniziale."""
    host = host.lower().lstrip(".")
    pattern = pattern.lower().strip()
    if pattern.startswith("*."):
        pattern = pattern[2:]
    pattern = pattern.lstrip(".")
    if not pattern:
        return False
    if pattern.startswith("http"):
        pattern = urlparse(pattern).netloc or pattern
    if "/" in pattern:
        pattern = pattern.split("/", 1)[0]
    return host == pattern or host.endswith("." + pattern)


def guess_filetype(url: str, mime: str = "") -> str:
    """Deduce l'estensione di un risultato dall'URL o dal MIME type."""
    path = urlparse(url).path
    if "." in path:
        candidate = path.rsplit(".", 1)[-1].lower()
        if 1 <= len(candidate) <= 6 and candidate.isalnum():
            return candidate
    mime = (mime or "").lower()
    mapping = {
        "application/pdf": "pdf",
        "application/msword": "doc",
        "application/vnd.ms-excel": "xls",
        "application/vnd.ms-powerpoint": "ppt",
        "text/csv": "csv",
        "application/json": "json",
        "text/plain": "txt",
        "application/zip": "zip",
    }
    if mime in mapping:
        return mapping[mime]
    if "wordprocessingml" in mime:
        return "docx"
    if "spreadsheetml" in mime:
        return "xlsx"
    if "presentationml" in mime:
        return "pptx"
    return ""


def verify(constraints: Constraints, url: str, title: str = "", mime: str = "") -> dict:
    """Verifica un singolo risultato contro i vincoli.

    Restituisce un dizionario ``vincolo -> True | False | None`` dove ``None``
    significa "non verificabile con i dati disponibili".
    """
    checks: dict[str, bool | None] = {}
    host = (urlparse(url).netloc or "").lower()
    title_l = (title or "").lower()
    url_l = (url or "").lower()

    if constraints.sites:
        checks["site"] = any(_host_matches(host, s) for s in constraints.sites)
    if constraints.exclude_sites:
        checks["-site"] = not any(_host_matches(host, s) for s in constraints.exclude_sites)
    if constraints.filetypes:
        found = guess_filetype(url, mime)
        checks["filetype"] = found in constraints.filetypes if found else None
    if constraints.inurl:
        checks["inurl"] = all(term in url_l for term in constraints.inurl)
    if constraints.exclude_inurl:
        checks["-inurl"] = not any(term in url_l for term in constraints.exclude_inurl)
    if constraints.intitle:
        checks["intitle"] = all(term in title_l for term in constraints.intitle) if title_l else None

    return checks


def compliance(checks: dict) -> str:
    """Riassume l'esito della verifica: ok | parziale | fuori | sconosciuto."""
    if not checks:
        return "sconosciuto"
    values = list(checks.values())
    if any(v is False for v in values):
        return "fuori"
    if all(v is True for v in values):
        return "ok"
    return "parziale"


def to_natural_language(query: str) -> str:
    """Traduce una query in istruzioni per un motore di ricerca agentico.

    Gli operatori dork non vengono eseguiti letteralmente dai motori basati su
    modelli linguistici: esplicitarli come vincoli in linguaggio naturale
    migliora sensibilmente la pertinenza dei risultati.
    """
    constraints = extract(query)
    if constraints.is_empty():
        # Nessun operatore da tradurre: il preambolo aggiungerebbe solo rumore.
        return query

    lines: list[str] = []
    if constraints.terms:
        lines.append("Argomento: " + " ".join(constraints.terms))
    if constraints.sites:
        lines.append("Includi soltanto risultati ospitati su: " + ", ".join(constraints.sites))
    if constraints.exclude_sites:
        lines.append("Escludi i domini: " + ", ".join(constraints.exclude_sites))
    if constraints.filetypes:
        lines.append("Restituisci soltanto file con estensione: " + ", ".join(constraints.filetypes))
    if constraints.inurl:
        lines.append("L'URL deve contenere: " + ", ".join(constraints.inurl))
    if constraints.exclude_inurl:
        lines.append("L'URL non deve contenere: " + ", ".join(constraints.exclude_inurl))
    if constraints.intitle:
        lines.append("Il titolo deve contenere: " + ", ".join(constraints.intitle))

    if not lines:
        return query

    return (
        "Esegui una ricerca documentale rispettando rigorosamente questi vincoli.\n"
        + "\n".join("- " + line for line in lines)
        + "\n\nQuery originale in sintassi dork: " + query
        + "\n\nRestituisci gli URL diretti dei documenti trovati."
    )
