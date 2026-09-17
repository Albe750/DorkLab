"""Test del modulo di audit difensivo: perimetro e autorizzazione."""

import pytest

from dorklab import audit


def test_normalizzazione_dominio():
    assert audit.normalize_domain("https://www.Esempio.it/path?x=1") == "esempio.it"
    assert audit.normalize_domain("  ESEMPIO.IT  ") == "esempio.it"


def test_validazione_dominio():
    assert audit.is_valid_domain("esempio.it")
    assert audit.is_valid_domain("sub.esempio.co.uk")
    assert not audit.is_valid_domain("localhost")
    assert not audit.is_valid_domain("non valido!")
    assert not audit.is_valid_domain("")


def test_senza_autorizzazione_non_si_genera_il_piano():
    with pytest.raises(audit.AuthorizationError):
        audit.build_plan("esempio.it", ["doc_esposti"], authorized=False)


def test_dominio_non_valido_rifiutato():
    with pytest.raises(audit.AuthorizationError):
        audit.build_plan("non valido!", ["doc_esposti"], authorized=True)


def test_ogni_query_del_piano_ha_il_perimetro():
    """Ogni query di audit deve avere un site: e menzionare il dominio.

    E' la garanzia centrale del modulo: nessuna query generata puo' essere una
    ricerca generica, ne' una ricerca su un dominio altrui slegata dal
    perimetro autorizzato.
    """
    tutti = [check["id"] for check in __import__(
        "dorklab.catalog", fromlist=["x"]).audit_checks()]
    plan = audit.build_plan("esempio.it", tutti, authorized=True)
    assert plan.queries
    for item in plan.queries:
        assert "site:" in item.query, item.query
        assert "esempio.it" in item.query.lower(), item.query


def test_perimetro_di_terze_parti_porta_con_se_il_dominio():
    """I controlli sullo storage cloud cercano su domini altrui.

    Il loro site: punta al provider, non al dominio verificato: il dominio
    autorizzato deve comunque comparire come termine obbligatorio.
    """
    query = audit.enforce_scope("site:s3.amazonaws.com", "esempio.it")
    assert query == "site:s3.amazonaws.com esempio.it"


def test_perimetro_di_terze_parti_non_duplica_il_dominio():
    query = audit.enforce_scope("site:s3.amazonaws.com esempio.it", "esempio.it")
    assert query.count("esempio.it") == 1


def test_perimetro_aggiunto_se_mancante():
    assert audit.enforce_scope('intitle:"index of"', "esempio.it") \
        == 'site:esempio.it intitle:"index of"'


def test_perimetro_esistente_non_duplicato():
    query = audit.enforce_scope("site:s3.amazonaws.com esempio.it", "esempio.it")
    assert query.count("site:") == 1


def test_ordinamento_per_gravita():
    plan = audit.build_plan("esempio.it", ["doc_esposti", "backup_archivi"],
                            authorized=True)
    severita = [q.severity for q in plan.by_severity()]
    assert severita[0] == "critica"
    assert severita[-1] == "info"


def test_riepilogo():
    plan = audit.build_plan("esempio.it", ["directory_listing"], authorized=True)
    plan.queries[0].executed = True
    plan.queries[0].hits = 4
    riepilogo = plan.summary()
    assert riepilogo["eseguite"] == 1
    assert riepilogo["con_risultati"] == 1
    assert plan.findings()[0].hits == 4


def test_ghdb_riceve_il_perimetro():
    query = audit.scoped_ghdb_query('intitle:"index of"', "esempio.it", authorized=True)
    assert query.startswith("site:esempio.it")


def test_ghdb_senza_autorizzazione():
    with pytest.raises(audit.AuthorizationError):
        audit.scoped_ghdb_query("intitle:x", "esempio.it", authorized=False)
