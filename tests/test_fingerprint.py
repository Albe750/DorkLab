"""Test del riconoscimento tecnologia e dei dork suggeriti."""

from dorklab import fingerprint


def test_rileva_aspnet_da_url():
    found = fingerprint.detect_from_urls([
        "https://x.it/login.aspx", "https://x.it/ScriptResource.axd"])
    assert "aspnet" in found


def test_rileva_wordpress_da_url():
    found = fingerprint.detect_from_urls([
        "https://x.it/wp-content/uploads/a.pdf", "https://x.it/wp-login.php"])
    assert "wordpress" in found


def test_rileva_da_intestazioni():
    found = fingerprint.detect_from_headers({
        "Server": "Microsoft-IIS/10.0", "X-Powered-By": "ASP.NET",
        "Set-Cookie": "ASP.NET_SessionId=abc"})
    assert "aspnet" in found


def test_rileva_php_da_powered_by():
    found = fingerprint.detect_from_headers({"X-Powered-By": "PHP/8.1"})
    assert "php" in found


def test_dork_suggeriti_contengono_il_dominio():
    dorks = fingerprint.suggested_dorks(["aspnet"], "esempio.it")
    assert dorks
    assert all("esempio.it" in d.query for d in dorks)
    assert any("ext:config" in d.query for d in dorks)


def test_dork_generici_sempre_presenti():
    # anche senza tecnologia rilevata, ci sono i dork "always"
    dorks = fingerprint.suggested_dorks([], "esempio.it")
    assert any(d.tech == "generico" for d in dorks)
    assert any("filetype:pdf" in d.query for d in dorks)


def test_report_da_url_senza_rete():
    from dorklab.config import Config

    report = fingerprint.analyze(
        "x.it", ["https://x.it/a.aspx", "https://x.it/b.axd"],
        Config(), probe=False)
    assert report.found
    assert report.matches[0].tech_id == "aspnet"
    assert report.dorks()


def test_dork_deduplicati():
    dorks = fingerprint.suggested_dorks(["apache", "nginx"], "x.it")
    queries = [d.query for d in dorks]
    assert len(queries) == len(set(queries))   # "index of" compare una volta sola
