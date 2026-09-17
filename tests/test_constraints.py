"""Test dell'estrazione e verifica dei vincoli."""

from dorklab import constraints


def test_estrazione_base():
    found = constraints.extract('site:a.it filetype:pdf -inurl:tag "frase"')
    assert found.sites == ["a.it"]
    assert found.filetypes == ["pdf"]
    assert found.exclude_inurl == ["tag"]
    assert "frase" in found.terms


def test_estrazione_dentro_gruppo():
    """Le parentesi di raggruppamento non devono finire nel valore."""
    found = constraints.extract("(filetype:pdf OR filetype:docx)")
    assert found.filetypes == ["pdf", "docx"]


def test_site_negato():
    found = constraints.extract("-site:pinterest.com test")
    assert found.exclude_sites == ["pinterest.com"]
    assert found.sites == []


def test_verifica_dominio_e_sottodominio():
    found = constraints.extract("site:esempio.it")
    assert constraints.verify(found, "https://www.esempio.it/a")["site"] is True
    assert constraints.verify(found, "https://esempio.it/a")["site"] is True
    assert constraints.verify(found, "https://altro.it/a")["site"] is False


def test_verifica_non_confonde_domini_simili():
    found = constraints.extract("site:esempio.it")
    assert constraints.verify(found, "https://nonesempio.it/a")["site"] is False


def test_site_con_jolly():
    found = constraints.extract("site:*.esempio.it")
    assert constraints.verify(found, "https://blog.esempio.it/x")["site"] is True


def test_filetype_non_verificabile():
    found = constraints.extract("filetype:pdf")
    checks = constraints.verify(found, "https://a.it/pagina-senza-estensione")
    assert checks["filetype"] is None


def test_filetype_dal_mime():
    found = constraints.extract("filetype:pdf")
    checks = constraints.verify(found, "https://a.it/scarica", mime="application/pdf")
    assert checks["filetype"] is True


def test_giudizio_complessivo():
    found = constraints.extract("site:a.it filetype:pdf")
    assert constraints.compliance(constraints.verify(found, "https://a.it/x.pdf")) == "ok"
    assert constraints.compliance(constraints.verify(found, "https://b.it/x.pdf")) == "fuori"
    assert constraints.compliance(constraints.verify(found, "https://a.it/x")) == "parziale"


def test_traduzione_in_linguaggio_naturale():
    testo = constraints.to_natural_language("site:a.it filetype:pdf bilancio")
    assert "a.it" in testo and "pdf" in testo and "bilancio" in testo


def test_traduzione_query_senza_vincoli():
    assert constraints.to_natural_language("solo parole") == "solo parole"


def test_deduzione_estensione():
    assert constraints.guess_filetype("https://a.it/doc.PDF") == "pdf"
    assert constraints.guess_filetype("https://a.it/x", "application/pdf") == "pdf"
    assert constraints.guess_filetype("https://a.it/pagina") == ""
