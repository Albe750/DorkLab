"""Catalogo GHDB: voci locali e importazione di elenchi esterni.

Il catalogo incluso e' curato e funziona senza rete. L'aggiornamento online e'
opzionale e best-effort: le sorgenti pubbliche cambiano formato nel tempo, per
cui un fallimento non deve compromettere l'uso dell'applicazione.
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

from . import catalog
from .paths import DATA_DIR, data_dir

USER_CATALOG = "ghdb_user.json"


@dataclass
class GhdbEntry:
    id: str
    category: str
    title: str
    dork: str
    severity: str = "media"
    note: str = ""
    remediation: str = ""
    scope_required: bool = True
    source: str = "locale"

    def to_dict(self) -> dict:
        return asdict(self)


def _seed() -> dict:
    with (DATA_DIR / "ghdb_seed.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def categories() -> list[dict]:
    return _seed()["categories"]


def category_label(category_id: str) -> str:
    for category in categories():
        if category["id"] == category_id:
            return category["label"]
    return category_id


def _user_path() -> Path:
    return data_dir() / USER_CATALOG


def load_user_entries() -> list[GhdbEntry]:
    path = _user_path()
    if not path.exists():
        return []
    try:
        with path.open(encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    return [GhdbEntry(**{k: v for k, v in item.items()
                         if k in GhdbEntry.__dataclass_fields__})
            for item in payload.get("entries", [])]


def save_user_entries(entries: Iterable[GhdbEntry]) -> int:
    path = _user_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    items = [entry.to_dict() for entry in entries]
    with path.open("w", encoding="utf-8") as handle:
        json.dump({"updated": time.strftime("%Y-%m-%d"), "entries": items},
                  handle, indent=2, ensure_ascii=False)
    return len(items)


def entries(include_user: bool = True) -> list[GhdbEntry]:
    """Tutte le voci disponibili: catalogo incluso piu' quelle importate."""
    items = [GhdbEntry(**{k: v for k, v in raw.items()
                          if k in GhdbEntry.__dataclass_fields__})
             for raw in _seed()["entries"]]
    if include_user:
        known = {item.id for item in items}
        for entry in load_user_entries():
            if entry.id not in known:
                items.append(entry)
    return items


def search(term: str, category: str = "", severity: str = "") -> list[GhdbEntry]:
    """Filtra le voci per testo libero, categoria e gravita'."""
    term = (term or "").strip().lower()
    result = []
    for entry in entries():
        if category and entry.category != category:
            continue
        if severity and entry.severity != severity:
            continue
        if term:
            haystack = " ".join((entry.title, entry.dork, entry.note,
                                 entry.remediation,
                                 category_label(entry.category))).lower()
            if term not in haystack:
                continue
        result.append(entry)
    return result


# ------------------------------------------------------------- importazione
def import_file(path: str | Path) -> list[GhdbEntry]:
    """Importa voci da un file JSON o CSV.

    Formati accettati:

    * JSON: un oggetto con chiave ``entries`` oppure una lista di oggetti.
    * CSV: intestazioni che includano almeno ``dork`` (o ``query``) e
      ``title`` (o ``titolo``).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix.lower() == ".csv":
        rows = _read_csv(path)
    else:
        rows = _read_json(path)

    imported: list[GhdbEntry] = []
    for index, row in enumerate(rows, start=1):
        dork = (row.get("dork") or row.get("query") or row.get("url_title") or "").strip()
        if not dork:
            continue
        title = (row.get("title") or row.get("titolo") or dork)[:160]
        imported.append(GhdbEntry(
            id=str(row.get("id") or "imp-%s-%03d" % (path.stem[:8], index)),
            category=str(row.get("category") or row.get("categoria") or "juicy_info"),
            title=title,
            dork=dork,
            severity=str(row.get("severity") or "media"),
            note=str(row.get("note") or row.get("description") or ""),
            remediation=str(row.get("remediation") or ""),
            source=path.name,
        ))
    return imported


def _read_json(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("entries", "results", "data", "dorks"):
            if isinstance(payload.get(key), list):
                return [item for item in payload[key] if isinstance(item, dict)]
    return []


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        return [
            {(k or "").strip().lower(): (v or "").strip()
             for k, v in row.items()}
            for row in csv.DictReader(handle, dialect=dialect)
        ]


def merge_user_entries(new_entries: list[GhdbEntry]) -> int:
    """Aggiunge le voci importate al catalogo utente, evitando i duplicati."""
    existing = {entry.dork.strip().lower(): entry for entry in load_user_entries()}
    builtin = {entry.dork.strip().lower() for entry in entries(include_user=False)}
    added = 0
    for entry in new_entries:
        key = entry.dork.strip().lower()
        if key in existing or key in builtin:
            continue
        existing[key] = entry
        added += 1
    save_user_entries(existing.values())
    return added
