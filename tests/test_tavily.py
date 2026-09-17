"""Test della logica di profondita' del motore Tavily."""

from dorklab.providers.agentic import TavilyProvider, _allowed_domains


def test_nessuna_variante_sotto_il_tetto():
    provider = TavilyProvider()
    query = "site:a.it (filetype:pdf OR filetype:docx) test"
    assert provider._variants(query, 20) == [query]


def test_varianti_per_estensione():
    provider = TavilyProvider()
    varianti = provider._variants("site:a.it (filetype:pdf OR filetype:docx) test", 60)
    assert len(varianti) == 3
    assert "filetype:pdf test" in varianti[1]
    assert "filetype:docx test" in varianti[2]


def test_varianti_per_dominio():
    provider = TavilyProvider()
    varianti = provider._variants("(site:a.it OR site:b.it) filetype:pdf", 60)
    assert any("site:a.it" in v and "site:b.it" not in v for v in varianti[1:])


def test_nessuna_variante_senza_alternative():
    provider = TavilyProvider()
    query = "site:a.it filetype:pdf test"
    assert provider._variants(query, 100) == [query]


def test_domini_ammessi_ed_esclusi():
    ammessi, esclusi = _allowed_domains("site:a.it -site:spam.com test")
    assert ammessi == ["a.it"]
    assert esclusi == ["spam.com"]


def test_domini_non_validi_scartati():
    """Nomi a etichetta singola e TLD nudi non sono accettati dalle API."""
    ammessi, _ = _allowed_domains("site:localhost site:a.it")
    assert ammessi == ["a.it"]


def test_jolly_normalizzato():
    ammessi, _ = _allowed_domains("site:*.esempio.it")
    assert ammessi == ["esempio.it"]
