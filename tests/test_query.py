"""Test del modello della query: composizione, parsing e round-trip."""

import pytest

from dorklab.query import DorkQuery, Token, group_of, parse


def test_operatore_semplice():
    query = DorkQuery([Token(kind="operator", operator="site", value="esempio.it")])
    assert query.to_string() == "site:esempio.it"


def test_operatore_negato():
    query = DorkQuery([Token(kind="operator", operator="inurl", value="tag", negated=True)])
    assert query.to_string() == "-inurl:tag"


def test_valore_con_spazi_viene_virgolettato():
    query = DorkQuery([Token(kind="operator", operator="intitle", value="rapporto di prova")])
    assert query.to_string() == 'intitle:"rapporto di prova"'


def test_token_disattivato_non_compare():
    query = DorkQuery([
        Token(kind="operator", operator="site", value="a.it"),
        Token(kind="term", value="escluso", enabled=False),
    ])
    assert query.to_string() == "site:a.it"


def test_token_senza_valore_viene_ignorato():
    query = DorkQuery([
        Token(kind="operator", operator="site", value="a.it"),
        Token(kind="operator", operator="filetype", value=""),
    ])
    assert query.to_string() == "site:a.it"


def test_or_esplicito():
    query = DorkQuery([
        Token(kind="term", value="pdf"),
        Token(kind="term", value="docx", joiner="OR"),
    ])
    assert query.to_string() == "pdf OR docx"


def test_gruppo_di_estensioni():
    token = group_of(["pdf", "docx"], "filetype")
    assert token.render() == "(filetype:pdf OR filetype:docx)"


def test_gruppo_negato():
    token = group_of(["pdf"], "filetype")
    token.negated = True
    assert token.render() == "-(filetype:pdf)"


@pytest.mark.parametrize("testo", [
    "site:esempio.it filetype:pdf",
    'site:esempio.it (filetype:pdf OR filetype:docx) "rapporto di prova" -inurl:tag',
    'intitle:"index of" -site:github.com backup',
    "pdf OR docx OR xlsx",
])
def test_round_trip(testo):
    """Analizzare e ricomporre una query deve restituire la stessa stringa."""
    assert DorkQuery.from_text(testo).to_string() == testo


def test_parsing_riconosce_gli_operatori():
    tokens = parse("site:a.it -filetype:pdf libero")
    assert [t.kind for t in tokens] == ["operator", "operator", "term"]
    assert tokens[1].negated is True
    assert tokens[2].value == "libero"


def test_parsing_gruppo():
    tokens = parse("(filetype:pdf OR filetype:doc) test")
    assert tokens[0].kind == "group"
    assert tokens[0].value == "filetype:pdf OR filetype:doc"


def test_parsing_frase_esatta():
    tokens = parse('"una frase lunga"')
    assert tokens[0].quoted is True
    assert tokens[0].value == "una frase lunga"


def test_parola_non_operatore_resta_termine():
    """Un due punti che non introduce un operatore noto non va interpretato."""
    tokens = parse("orario:14:30")
    assert tokens[0].kind == "term"


def test_sposta_token():
    a = Token(kind="term", value="a")
    b = Token(kind="term", value="b")
    query = DorkQuery([a, b])
    query.move(b, -1)
    assert query.to_string() == "b a"


def test_serializzazione():
    query = DorkQuery([Token(kind="operator", operator="site", value="a.it")])
    ricostruita = DorkQuery.from_dict(query.to_dict())
    assert ricostruita.to_string() == query.to_string()
