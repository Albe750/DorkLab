"""Caricamento del catalogo statico (operatori, tipi di file, ricette, audit)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from .paths import DATA_DIR


@lru_cache(maxsize=None)
def _load(name: str) -> dict[str, Any]:
    path = DATA_DIR / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


# --------------------------------------------------------------------- operatori
def operator_categories() -> list[dict]:
    return _load("operators.json")["categories"]


def operators() -> list[dict]:
    return _load("operators.json")["operators"]


def operators_by_category() -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {c["id"]: [] for c in operator_categories()}
    for operator in operators():
        grouped.setdefault(operator["category"], []).append(operator)
    return grouped


def operator(operator_id: str) -> dict | None:
    for item in operators():
        if item["id"] == operator_id:
            return item
    return None


def supports(operator_id: str, engine: str) -> bool:
    """Indica se un operatore e' supportato dal motore selezionato."""
    item = operator(operator_id)
    if not item:
        return False
    engines = item.get("engines") or []
    return not engines or engine in engines


# --------------------------------------------------------------------- filetype
def filetype_groups() -> list[dict]:
    return _load("filetypes.json")["groups"]


def filetype_group(group_id: str) -> dict | None:
    for group in filetype_groups():
        if group["id"] == group_id:
            return group
    return None


def all_extensions() -> list[str]:
    seen: list[str] = []
    for group in filetype_groups():
        for ext in group["extensions"]:
            if ext not in seen:
                seen.append(ext)
    return seen


# ---------------------------------------------------------------------- ricette
def recipes() -> list[dict]:
    return _load("recipes.json")["recipes"]


def recipe_placeholders() -> dict[str, dict]:
    return _load("recipes.json")["placeholders"]


def recipe(recipe_id: str) -> dict | None:
    for item in recipes():
        if item["id"] == recipe_id:
            return item
    return None


def render_recipe(recipe_id: str, values: dict[str, str]) -> str:
    """Applica i valori ai segnaposto di una ricetta."""
    item = recipe(recipe_id)
    if not item:
        return ""
    text = item["template"]
    for field_name in item.get("fields", []):
        text = text.replace("{%s}" % field_name, values.get(field_name, "").strip())
    return " ".join(text.split())


# ------------------------------------------------------------------------ audit
def audit_checks() -> list[dict]:
    return _load("audit_profiles.json")["checks"]


def audit_check(check_id: str) -> dict | None:
    for check in audit_checks():
        if check["id"] == check_id:
            return check
    return None


def severities() -> dict[str, dict]:
    return _load("audit_profiles.json")["severities"]


def severity_order(name: str) -> int:
    return severities().get(name, {}).get("order", 99)
