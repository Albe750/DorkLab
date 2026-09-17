"""Estrazione dei metadati dai documenti scaricati.

I formati OOXML (docx/xlsx/pptx) e ODF (odt/ods/odp) sono archivi ZIP con un
file XML di proprieta': si leggono con la sola libreria standard. Per i PDF
viene usato ``pypdf`` se disponibile, altrimenti si ricade su una lettura
minimale del dizionario /Info.

I metadati sono spesso la parte piu' interessante di un documento pubblico:
rivelano autori, software, percorsi interni e date di revisione. In un audit
difensivo servono a capire quanto si sta esponendo senza accorgersene.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

OOXML_EXT = {".docx", ".xlsx", ".pptx", ".docm", ".xlsm", ".pptm"}
ODF_EXT = {".odt", ".ods", ".odp", ".odg"}

_OOXML_FIELDS = {
    "creator": "autore",
    "lastModifiedBy": "ultima modifica di",
    "title": "titolo",
    "subject": "oggetto",
    "description": "descrizione",
    "keywords": "parole chiave",
    "created": "creato",
    "modified": "modificato",
    "revision": "revisione",
    "category": "categoria",
    "company": "organizzazione",
    "Company": "organizzazione",
    "Application": "applicazione",
    "AppVersion": "versione applicazione",
    "Manager": "responsabile",
}

_ODF_FIELDS = {
    "creator": "autore",
    "initial-creator": "autore iniziale",
    "title": "titolo",
    "subject": "oggetto",
    "description": "descrizione",
    "generator": "applicazione",
    "creation-date": "creato",
    "date": "modificato",
    "editing-cycles": "revisioni",
}


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _from_ooxml(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            for member in ("docProps/core.xml", "docProps/app.xml"):
                if member not in archive.namelist():
                    continue
                root = ElementTree.fromstring(archive.read(member))
                for child in root.iter():
                    name = _strip_ns(child.tag)
                    if name in _OOXML_FIELDS and (child.text or "").strip():
                        found[_OOXML_FIELDS[name]] = child.text.strip()
    except (zipfile.BadZipFile, ElementTree.ParseError, OSError, KeyError):
        return found
    return found


def _from_odf(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            if "meta.xml" not in archive.namelist():
                return found
            root = ElementTree.fromstring(archive.read("meta.xml"))
            for child in root.iter():
                name = _strip_ns(child.tag)
                if name in _ODF_FIELDS and (child.text or "").strip():
                    found[_ODF_FIELDS[name]] = child.text.strip()
                if name == "generator" and (child.text or "").strip():
                    found["applicazione"] = child.text.strip()
    except (zipfile.BadZipFile, ElementTree.ParseError, OSError, KeyError):
        return found
    return found


def _from_pdf(path: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return _from_pdf_raw(path)

    try:
        reader = PdfReader(str(path))
        info = reader.metadata or {}
        mapping = {
            "/Author": "autore", "/Title": "titolo", "/Subject": "oggetto",
            "/Creator": "creato con", "/Producer": "prodotto da",
            "/CreationDate": "creato", "/ModDate": "modificato",
            "/Keywords": "parole chiave", "/Company": "organizzazione",
        }
        for key, label in mapping.items():
            value = info.get(key)
            if value:
                found[label] = str(value).strip()
        found["pagine"] = str(len(reader.pages))
        if reader.is_encrypted:
            found["cifrato"] = "si"
    except Exception:  # noqa: BLE001 - un PDF malformato non deve fermare tutto
        return _from_pdf_raw(path)
    return found


_PDF_INFO_RE = re.compile(
    rb"/(Author|Title|Subject|Creator|Producer|CreationDate|ModDate)\s*\(([^)]{0,300})\)")


def _from_pdf_raw(path: Path) -> dict[str, str]:
    """Lettura minimale del dizionario /Info senza dipendenze esterne."""
    labels = {
        b"Author": "autore", b"Title": "titolo", b"Subject": "oggetto",
        b"Creator": "creato con", b"Producer": "prodotto da",
        b"CreationDate": "creato", b"ModDate": "modificato",
    }
    found: dict[str, str] = {}
    try:
        blob = path.read_bytes()[:2_000_000]
    except OSError:
        return found
    for key, value in _PDF_INFO_RE.findall(blob):
        label = labels.get(key)
        if label and value.strip():
            found[label] = value.decode("utf-8", "replace").strip()
    return found


def extract(path: str | Path) -> dict[str, str]:
    """Restituisce i metadati del file indicato, per quanto ricavabili."""
    path = Path(path)
    if not path.is_file():
        return {}
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        found = _from_pdf(path)
    elif suffix in OOXML_EXT:
        found = _from_ooxml(path)
    elif suffix in ODF_EXT:
        found = _from_odf(path)
    else:
        found = {}

    try:
        found.setdefault("dimensione", "%.1f KB" % (path.stat().st_size / 1024))
    except OSError:
        pass
    return found


def summarize(entries: list[dict[str, str]]) -> dict[str, list[tuple[str, int]]]:
    """Aggrega i metadati di piu' documenti.

    Evidenzia autori ricorrenti, software usati e organizzazioni: e' la vista
    che rende utile un'estrazione documentale massiva.
    """
    buckets = ("autore", "ultima modifica di", "creato con", "prodotto da",
               "applicazione", "organizzazione")
    counters: dict[str, dict[str, int]] = {b: {} for b in buckets}

    for entry in entries:
        for bucket in buckets:
            value = (entry.get(bucket) or "").strip()
            if value:
                counters[bucket][value] = counters[bucket].get(value, 0) + 1

    return {
        bucket: sorted(values.items(), key=lambda kv: (-kv[1], kv[0]))
        for bucket, values in counters.items() if values
    }
