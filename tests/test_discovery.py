"""Test delle fonti di scoperta di contenuto non indicizzato."""

from unittest.mock import patch

import pytest

from dorklab import discovery
from dorklab.config import Config
from dorklab.discovery.base import DiscoveryError


@pytest.fixture
def config():
    return Config()


def test_registro_fonti():
    fonti = discovery.all_sources()
    assert len(fonti) >= 6
    ids = [s.id for s in fonti]
    assert "wayback" in ids and "crtsh" in ids and "probe" in ids
    assert len(ids) == len(set(ids))


def test_classi_e_gate():
    wayback = discovery.get("wayback")
    assert not wayback.touches_target
    assert not wayback.requires_authorization

    probe = discovery.get("probe")
    assert probe.touches_target
    assert probe.requires_authorization


def test_wayback_parsing(config):
    rows = [
        ["original", "timestamp", "mimetype", "statuscode", "digest"],
        ["https://x.it/a.pdf", "20190101000000", "application/pdf", "200", "A"],
        ["https://x.it/b.html", "20200101000000", "text/html", "200", "B"],
        ["https://x.it/a.pdf", "20210101000000", "application/pdf", "200", "A"],
    ]
    with patch("dorklab.discovery.wayback.get_json", return_value=rows):
        response = discovery.get("wayback").discover("x.it", config=config)
    urls = [u.url for u in response.urls]
    assert urls.count("https://x.it/a.pdf") == 1   # deduplicato
    assert len(response.urls) == 2


def test_wayback_filtra_per_tipo(config):
    rows = [
        ["original", "timestamp", "mimetype", "statuscode", "digest"],
        ["https://x.it/a.pdf", "20190101000000", "application/pdf", "200", "A"],
        ["https://x.it/b.html", "20200101000000", "text/html", "200", "B"],
    ]
    with patch("dorklab.discovery.wayback.get_json", return_value=rows):
        response = discovery.get("wayback").discover("x.it", config=config, filetypes=["pdf"])
    assert [u.filetype for u in response.urls] == ["pdf"]


def test_wayback_costruisce_copia_archiviata(config):
    rows = [
        ["original", "timestamp", "mimetype", "statuscode", "digest"],
        ["https://x.it/a.pdf", "20190312101500", "application/pdf", "200", "A"],
    ]
    with patch("dorklab.discovery.wayback.get_json", return_value=rows):
        response = discovery.get("wayback").discover("x.it", config=config)
    item = response.urls[0]
    assert item.has_archive
    assert "web.archive.org/web/20190312101500id_/" in item.archived_url


def test_crtsh_estrae_sottodomini(config):
    records = [
        {"name_value": "*.x.it\nwww.x.it"},
        {"name_value": "staging.x.it"},
        {"name_value": "vpn.x.it\nstaging.x.it"},
        {"name_value": "estraneo.com"},
    ]
    with patch("dorklab.discovery.crtsh.get_json", return_value=records):
        response = discovery.get("crtsh").discover("x.it", config=config)
    hosts = sorted(u.title for u in response.urls)
    assert hosts == ["staging.x.it", "vpn.x.it", "www.x.it", "x.it"]


def test_sitemap_legge_robots_e_sitemap(config):
    robots = b"Disallow: /admin/\nSitemap: https://x.it/sitemap.xml\n"
    smap = (b'<?xml version="1.0"?><urlset '
            b'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            b'<url><loc>https://x.it/doc/a.pdf</loc></url></urlset>')

    def fake(url, **kwargs):
        if "robots" in url:
            return 200, robots
        if url.endswith("sitemap.xml"):
            return 200, smap
        return 404, b""

    with patch("dorklab.discovery.sitemap.get_text", side_effect=fake):
        response = discovery.get("sitemap").discover("x.it", config=config)
    urls = {u.url for u in response.urls}
    assert "https://x.it/admin/" in urls        # dal Disallow di robots.txt
    assert "https://x.it/doc/a.pdf" in urls      # dal sitemap


def test_sitemap_index_ricorsivo(config):
    index = (b'<?xml version="1.0"?><sitemapindex '
             b'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
             b'<sitemap><loc>https://x.it/sub.xml</loc></sitemap></sitemapindex>')
    sub = (b'<?xml version="1.0"?><urlset '
           b'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
           b'<url><loc>https://x.it/pagina.html</loc></url></urlset>')

    def fake(url, **kwargs):
        if "robots" in url:
            return 404, b""
        if url.endswith("/sitemap.xml"):
            return 200, index
        if url.endswith("/sub.xml"):
            return 200, sub
        return 404, b""

    with patch("dorklab.discovery.sitemap.get_text", side_effect=fake):
        response = discovery.get("sitemap").discover("x.it", config=config)
    assert any(u.url == "https://x.it/pagina.html" for u in response.urls)


def test_probe_richiede_autorizzazione(config):
    with pytest.raises(DiscoveryError):
        discovery.get("probe").discover("x.it", config=config, authorized=False)


def test_wordlist_caricata():
    from dorklab.discovery.probe import load_wordlist

    parole = load_wordlist()
    assert len(parole) > 50
    assert all(not p.startswith("#") for p in parole)
    assert ".env" in parole and "backup.zip" in parole


def test_conversione_in_risultati_preferendo_archivio(config):
    rows = [
        ["original", "timestamp", "mimetype", "statuscode", "digest"],
        ["https://x.it/a.pdf", "20190101000000", "application/pdf", "200", "A"],
    ]
    with patch("dorklab.discovery.wayback.get_json", return_value=rows):
        response = discovery.get("wayback").discover("x.it", config=config)

    live = discovery.to_search_results(response, prefer_archived=False)
    archived = discovery.to_search_results(response, prefer_archived=True)
    assert live[0].url == "https://x.it/a.pdf"
    assert "web.archive.org" in archived[0].url


def test_dedupe_preferisce_la_copia_archiviata():
    from dorklab.discovery.base import DiscoveredUrl, DiscoveryResponse

    senza = DiscoveryResponse(urls=[DiscoveredUrl(url="https://x.it/a.pdf", source="sitemap")])
    con = DiscoveryResponse(urls=[DiscoveredUrl(
        url="https://x.it/a.pdf", source="wayback", archived_url="http://web.archive.org/x")])
    merged = discovery.dedupe([senza, con])
    assert len(merged) == 1
    assert merged[0].has_archive


def _resp(status, ctype="text/html", length=""):
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.status_code = status
    mock.headers = {"Content-Type": ctype, "Content-Length": length}
    return mock


def test_probe_filtra_i_soft_404(config):
    """Un sito che risponde 200 a qualsiasi percorso non deve produrre falsi file."""
    from dorklab.discovery.probe import PathProbeSource

    config.set("request_delay", 0)

    def fake(url, **kwargs):
        if "nonesiste.xyzq" in url:          # baseline: 200 a un percorso inventato
            return _resp(200, "text/html", "5000")
        if url.endswith("backup.zip"):       # vero file: tipo diverso
            return _resp(200, "application/zip", "200000")
        if url.endswith("/admin/"):          # protetto: reale
            return _resp(403, "text/html", "1200")
        return _resp(200, "text/html", "5000")   # pagina generica per tutto il resto

    with patch("dorklab.discovery.probe.get", side_effect=fake):
        response = PathProbeSource().discover(
            "soft.example", config=config, authorized=True, limit=1000)

    assert response.meta["soft_404"] == "si"
    titoli = {u.title for u in response.urls}
    assert "/backup.zip" in titoli          # il vero file resta
    assert "/admin/" in titoli              # la risorsa protetta resta
    assert "/.env" not in titoli            # i falsi 200 spariscono
    assert response.meta["falsi_positivi_esclusi"] > 50


def test_probe_sito_con_404_corretti(config):
    """Se il sito fa 404 corretti, i 200 sono considerati reali."""
    from dorklab.discovery.probe import PathProbeSource

    config.set("request_delay", 0)

    def fake(url, **kwargs):
        if "nonesiste.xyzq" in url:
            return _resp(404, "text/html", "500")
        if url.endswith(".env"):
            return _resp(200, "text/plain", "300")
        return _resp(404, "text/html", "500")

    with patch("dorklab.discovery.probe.get", side_effect=fake):
        response = PathProbeSource().discover(
            "hard.example", config=config, authorized=True, limit=1000)

    assert response.meta["soft_404"] == "no"
    assert any(u.title == "/.env" for u in response.urls)


def test_downloader_applica_il_jitter():
    """Il Downloader con jitter varia la pausa entro i limiti attesi."""
    from dorklab.fetcher import Downloader

    dl = Downloader("/tmp/x", user_agent="t", delay=4.0, jitter=0.5)
    for _ in range(30):
        pause = dl._pause()
        assert 2.0 - 0.01 <= pause <= 6.0 + 0.01
