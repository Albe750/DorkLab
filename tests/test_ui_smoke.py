"""Collaudo dell'interfaccia: costruzione, interazioni e chiusura.

Viene saltato se non c'e' alcun binding Qt installato, cosi' la suite resta
eseguibile anche in un ambiente senza interfaccia grafica.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

qtcompat = pytest.importorskip("dorklab.qtcompat",
                               reason="nessun binding Qt installato")
QtWidgets = qtcompat.QtWidgets


@pytest.fixture(scope="module")
def app():
    application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield application


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    from dorklab.ui import MainWindow

    win = MainWindow()
    win.config.set("accepted_terms", True)
    yield win
    win.store.close()


def test_finestra_si_costruisce(window):
    assert window.tabs.count() == 5


def test_costruzione_query_da_bolle(window):
    from dorklab.query import Token, group_of

    builder = window.builder
    builder.add_token(Token(kind="operator", operator="site", value="a.it"), focus=False)
    builder.add_token(group_of(["pdf", "docx"], "filetype"), focus=False)
    builder.add_token(Token(kind="term", value="test"), focus=False)
    assert builder.query_text() == "site:a.it (filetype:pdf OR filetype:docx) test"
    assert len(builder._chips) == 3


def test_modalita_testo_round_trip(window):
    builder = window.builder
    originale = 'site:x.it (filetype:pdf OR filetype:csv) -inurl:tag "test"'
    builder.raw_toggle.setChecked(True)
    builder.preview.setPlainText(originale)
    builder.raw_toggle.setChecked(False)
    assert builder.query_text() == originale


def test_rimozione_e_spostamento_token(window):
    from dorklab.query import Token

    builder = window.builder
    builder.clear()
    builder.add_token(Token(kind="term", value="uno"), focus=False)
    builder.add_token(Token(kind="term", value="due"), focus=False)
    builder.move_token(builder.query.tokens[1], -1)
    assert builder.query_text() == "due uno"
    builder._remove_token(builder.query.tokens[0])
    assert builder.query_text() == "uno"


def test_gruppi_di_tipi_file(window):
    builder = window.builder
    builder.clear()
    builder._filetype_bubbles["documenti"].setChecked(True)
    builder._add_filetype_groups()
    assert "filetype:pdf" in builder.query_text()


def test_tutti_i_motori_selezionabili(window):
    from dorklab import providers

    builder = window.builder
    for provider in providers.all_providers():
        index = builder.provider_combo.findData(provider.id)
        assert index >= 0, provider.id
        builder.provider_combo.setCurrentIndex(index)
        assert builder.current_provider().id == provider.id


def test_audit_richiede_autorizzazione(window):
    tab = window.audit
    tab.domain_edit.setText("esempio.it")
    assert not tab.generate_button.isEnabled()
    tab.authorized.setChecked(True)
    assert tab.generate_button.isEnabled()


def test_audit_rifiuta_dominio_non_valido(window):
    tab = window.audit
    tab.authorized.setChecked(True)
    tab.domain_edit.setText("non valido!")
    assert not tab.generate_button.isEnabled()


def test_piano_di_audit_resta_nel_perimetro(window):
    tab = window.audit
    tab.domain_edit.setText("esempio.it")
    tab.authorized.setChecked(True)
    tab._set_all(True)
    tab.generate_plan()
    assert tab.plan and tab.plan.queries
    for item in tab.plan.queries:
        assert "site:" in item.query
        assert "esempio.it" in item.query.lower()


def test_risultati_mostrano_la_conformita(window):
    from dorklab import providers
    from dorklab.providers.base import SearchResponse, SearchResult

    response = providers.annotate(SearchResponse(
        provider="tavily", query="site:a.it filetype:pdf",
        results=[SearchResult(title="dentro", url="https://a.it/x.pdf"),
                 SearchResult(title="fuori", url="https://b.it/x.pdf")]))
    window.results.set_response(response)
    assert window.results.table.rowCount() == 2
    assert window.results.results[0].compliance == "ok"
    assert window.results.results[1].compliance == "fuori"


def test_catalogo_ghdb_popolato(window):
    assert window.ghdb.table.rowCount() > 40
    window.ghdb.search_edit.setText("password")
    assert window.ghdb.table.rowCount() > 0
