"""Protective dorking: verifica difensiva della propria esposizione.

Il principio e' semplice: gli stessi operatori usati per trovare informazioni
altrui servono, applicati al proprio dominio, a scoprire cosa si sta esponendo
senza saperlo. Per questo ogni query generata qui e' vincolata al dominio
autorizzato: il modulo non produce query prive di perimetro.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from . import catalog

_DOMAIN_RE = re.compile(
    r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$")


class AuthorizationError(PermissionError):
    """Sollevata quando manca la conferma di autorizzazione sul dominio."""


def normalize_domain(value: str) -> str:
    """Ripulisce quanto inserito dall'utente restituendo un dominio semplice."""
    value = (value or "").strip().lower()
    value = re.sub(r"^[a-z]+://", "", value)
    value = value.split("/", 1)[0].split("?", 1)[0]
    value = value.split("@")[-1]
    value = value.strip(". ")
    if value.startswith("www."):
        value = value[4:]
    return value


def is_valid_domain(value: str) -> bool:
    domain = normalize_domain(value)
    return bool(domain) and bool(_DOMAIN_RE.match(domain)) and len(domain) <= 253


@dataclass
class AuditQuery:
    """Una singola verifica pronta per essere eseguita."""

    check_id: str
    check_label: str
    severity: str
    query: str
    description: str
    why: str
    remediation: list[str] = field(default_factory=list)
    # compilati dopo l'esecuzione
    executed: bool = False
    hits: int = 0
    error: str = ""
    reviewed: bool = False
    note: str = ""

    @property
    def status(self) -> str:
        if self.error:
            return "errore"
        if not self.executed:
            return "da eseguire"
        if self.hits == 0:
            return "nessuna esposizione"
        return "da verificare"


@dataclass
class AuditPlan:
    """Piano completo di verifica per un dominio."""

    domain: str
    queries: list[AuditQuery] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def by_severity(self) -> list[AuditQuery]:
        return sorted(self.queries, key=lambda q: catalog.severity_order(q.severity))

    def findings(self) -> list[AuditQuery]:
        return [q for q in self.queries if q.executed and q.hits > 0]

    def summary(self) -> dict[str, int]:
        counts = {"totali": len(self.queries), "eseguite": 0, "con_risultati": 0, "errori": 0}
        for query in self.queries:
            if query.error:
                counts["errori"] += 1
            if query.executed:
                counts["eseguite"] += 1
                if query.hits > 0:
                    counts["con_risultati"] += 1
        return counts


def enforce_scope(query: str, domain: str) -> str:
    """Garantisce che la query resti legata al perimetro autorizzato.

    La garanzia e' duplice e vale per ogni query prodotta da questo modulo:
    la query contiene **sempre** un vincolo ``site:`` e menziona **sempre** il
    dominio autorizzato.

    Il caso non banale sono i controlli sullo storage cloud, del tipo
    ``site:s3.amazonaws.com esempio.it``: hanno gia' un ``site:``, ma su un
    dominio di terze parti, e servono proprio a cercare li' le menzioni del
    proprio dominio. Sostituire quel ``site:`` snaturerebbe il controllo;
    lasciarlo passare senza altri vincoli aprirebbe la porta a una query
    generica su un dominio altrui. Percio', quando il perimetro presente non e'
    quello autorizzato, il dominio viene aggiunto come termine obbligatorio.
    """
    domain = normalize_domain(domain)
    if not domain:
        raise AuthorizationError("Dominio non valido.")

    if re.search(r"\bsite:\S+", query):
        if domain.lower() not in query.lower():
            return "%s %s" % (query.strip(), domain)
        return query
    return "site:%s %s" % (domain, query)


def build_plan(domain: str, check_ids: list[str], *, authorized: bool) -> AuditPlan:
    """Costruisce il piano di verifica per il dominio indicato.

    ``authorized`` deve essere la conferma esplicita dell'utente di essere
    proprietario del dominio o di avere un'autorizzazione scritta a verificarlo.
    """
    if not authorized:
        raise AuthorizationError(
            "Serve la conferma di essere proprietari del dominio o di avere "
            "un'autorizzazione scritta a verificarlo."
        )
    if not is_valid_domain(domain):
        raise AuthorizationError("Dominio non valido: %r" % domain)

    domain = normalize_domain(domain)
    plan = AuditPlan(domain=domain)

    for check_id in check_ids:
        check = catalog.audit_check(check_id)
        if not check:
            continue
        for template in check["queries"]:
            query = template.replace("{domain}", domain)
            plan.queries.append(AuditQuery(
                check_id=check["id"],
                check_label=check["label"],
                severity=check["severity"],
                query=enforce_scope(query, domain),
                description=check["desc"],
                why=check["why"],
                remediation=list(check.get("remediation", [])),
            ))
    return plan


def scoped_ghdb_query(dork: str, domain: str, *, authorized: bool) -> str:
    """Applica il perimetro autorizzato a una voce del catalogo GHDB."""
    if not authorized:
        raise AuthorizationError("Conferma di autorizzazione mancante.")
    if not is_valid_domain(domain):
        raise AuthorizationError("Dominio non valido: %r" % domain)
    return enforce_scope(dork, normalize_domain(domain))
