"""Test della costruzione della query per Tavily.

Regressione del baco "0 risultati": a Tavily va passata una query di ricerca
concisa, non il blocco di istruzioni in linguaggio naturale ne' gli operatori
dork, che vengono invece passati come filtro di dominio.
"""

from dorklab.providers.agentic import _tavily_query


def test_estrae_termini_e_tipi():
    query = _tavily_query("site:unibo.it (filetype:pdf OR filetype:docx) metrologia")
    assert "metrologia" in query
    assert "pdf" in query
    assert "site:" not in query          # niente sintassi dork
    assert "unibo.it" not in query       # il dominio va nel filtro, non nella query


def test_query_mai_vuota_con_solo_filetype():
    query = _tavily_query("site:a.it filetype:pdf")
    assert query.strip()                 # non deve essere vuota: darebbe 0 risultati


def test_query_di_ripiego_sul_dominio():
    query = _tavily_query("site:esempio.it")
    assert "esempio.it" in query or query == "documenti pubblici"


def test_termini_liberi_conservati():
    query = _tavily_query('filetype:pdf "rapporto di prova" taratura')
    assert "rapporto di prova" in query
    assert "taratura" in query
