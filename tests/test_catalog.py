"""Test di integrita' del catalogo dati e del registro dei motori."""

from dorklab import catalog, ghdb, providers
from dorklab.config import Config


def test_operatori_hanno_i_campi_richiesti():
    categorie = {c["id"] for c in catalog.operator_categories()}
    identificativi = set()
    for operatore in catalog.operators():
        assert operatore["id"] not in identificativi, "id duplicato"
        identificativi.add(operatore["id"])
        assert operatore["category"] in categorie
        assert operatore["desc"]
        assert operatore["engines"]


def test_gruppi_di_file_non_vuoti():
    for gruppo in catalog.filetype_groups():
        assert gruppo["extensions"]
        assert gruppo["desc"]


def test_ricette_usano_solo_segnaposto_dichiarati():
    segnaposto = set(catalog.recipe_placeholders())
    for ricetta in catalog.recipes():
        for campo in ricetta.get("fields", []):
            assert campo in segnaposto
            assert "{%s}" % campo in ricetta["template"]


def test_render_ricetta():
    reso = catalog.render_recipe("doc_dominio", {"domain": "a.it", "topic": "test"})
    assert "site:a.it" in reso and "{domain}" not in reso


def test_controlli_audit_sono_coerenti():
    gravita = set(catalog.severities())
    for controllo in catalog.audit_checks():
        assert controllo["severity"] in gravita
        assert controllo["queries"]
        assert controllo["remediation"]
        for query in controllo["queries"]:
            assert "{domain}" in query, "ogni query di audit deve essere vincolata"


def test_catalogo_ghdb_coerente():
    categorie = {c["id"] for c in ghdb.categories()}
    for voce in ghdb.entries(include_user=False):
        assert voce.category in categorie
        assert voce.dork
        assert voce.remediation


def test_ricerca_ghdb():
    assert ghdb.search("password")
    assert ghdb.search("", category="passwords")
    assert not ghdb.search("stringa-che-non-esiste-12345")


def test_registro_motori():
    tutti = providers.all_providers()
    assert len(tutti) >= 15
    identificativi = [p.id for p in tutti]
    assert len(identificativi) == len(set(identificativi))
    for provider in tutti:
        assert provider.label
        assert provider.kind in providers.kinds()


def test_motori_browser_sempre_disponibili():
    config = Config()
    for provider in providers.by_kind("browser"):
        assert provider.available(config)
        assert provider.build_url("site:a.it test").startswith("http")


def test_motori_api_richiedono_credenziali():
    config = Config()
    for provider in providers.by_kind("api"):
        if provider.credentials:
            assert not provider.available(config)


def test_annotazione_risultati():
    from dorklab.providers.base import SearchResponse, SearchResult

    response = SearchResponse(query="site:a.it filetype:pdf", results=[
        SearchResult(url="https://a.it/x.pdf"),
        SearchResult(url="https://b.it/x.pdf"),
    ])
    providers.annotate(response)
    assert response.results[0].compliance == "ok"
    assert response.results[1].compliance == "fuori"


def test_deduplica():
    from dorklab.providers.base import SearchResponse, SearchResult

    uno = SearchResponse(results=[SearchResult(url="https://a.it/x")])
    due = SearchResponse(results=[SearchResult(url="https://a.it/x/"),
                                  SearchResult(url="https://a.it/y")])
    assert len(providers.dedupe([uno, due])) == 2
