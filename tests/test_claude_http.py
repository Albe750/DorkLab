"""Test del motore Claude senza il pacchetto 'anthropic' (via HTTP diretto).

Regressione: il motore agentico Claude richiedeva il pacchetto 'anthropic',
che non sempre e' installabile (per esempio in certi venv). Ora funziona con la
sola libreria 'requests', gia' dipendenza di DorkLab.
"""

import builtins
from unittest.mock import patch

import pytest

from dorklab.config import Config
from dorklab.providers import SearchError
from dorklab.providers.agentic import ClaudeAgenticProvider


@pytest.fixture
def config():
    cfg = Config()
    cfg.set_credential("anthropic_api_key", "sk-ant-test")
    return cfg


@pytest.fixture
def no_sdk():
    """Simula l'assenza del pacchetto 'anthropic'."""
    real_import = builtins.__import__

    def fake(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("simulato")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake):
        yield


def test_available_non_richiede_il_pacchetto(config):
    # available() deve dipendere solo dalla chiave, non dal pacchetto SDK
    assert ClaudeAgenticProvider().available(config)


def test_ricerca_via_http(config, no_sdk):
    payload = {
        "model": "claude-opus-5", "stop_reason": "end_turn",
        "content": [
            {"type": "text", "text": "Trovati due documenti."},
            {"type": "web_search_tool_result", "content": [
                {"type": "web_search_result", "url": "https://x.it/a.pdf", "title": "A"},
                {"type": "web_search_result", "url": "https://x.it/b.pdf", "title": "B"},
            ]},
        ],
    }
    with patch("dorklab.providers.http.post_json", return_value=payload):
        response = ClaudeAgenticProvider().search(
            "site:x.it filetype:pdf test", config=config, limit=10)
    assert response.meta["via"] == "HTTP diretto"
    assert [r.url for r in response.results] == ["https://x.it/a.pdf", "https://x.it/b.pdf"]
    assert "due documenti" in response.answer


def test_http_invia_richiesta_corretta(config, no_sdk):
    payload = {"model": "claude-opus-5", "stop_reason": "end_turn", "content": []}
    with patch("dorklab.providers.http.post_json", return_value=payload) as mock:
        ClaudeAgenticProvider().search("site:x.it filetype:pdf", config=config)
    call = mock.call_args
    assert call.args[0] == "https://api.anthropic.com/v1/messages"
    assert call.kwargs["headers"]["x-api-key"] == "sk-ant-test"
    assert call.kwargs["headers"]["anthropic-version"] == "2023-06-01"
    body = call.kwargs["json"]
    assert body["model"] == "claude-opus-5"
    assert body["tools"][0]["type"] == "web_search_20260209"
    assert body["tools"][0]["allowed_domains"] == ["x.it"]


def test_http_gestisce_pause_turn(config, no_sdk):
    # Prima risposta in pausa, seconda conclusa: i risultati si accumulano.
    primo = {"model": "claude-opus-5", "stop_reason": "pause_turn",
             "content": [{"type": "web_search_tool_result", "content": [
                 {"type": "web_search_result", "url": "https://x.it/1.pdf", "title": "1"}]}]}
    secondo = {"model": "claude-opus-5", "stop_reason": "end_turn",
               "content": [{"type": "web_search_tool_result", "content": [
                   {"type": "web_search_result", "url": "https://x.it/2.pdf", "title": "2"}]}]}
    with patch("dorklab.providers.http.post_json", side_effect=[primo, secondo]) as mock:
        response = ClaudeAgenticProvider().search("test", config=config)
    assert mock.call_count == 2
    assert {r.url for r in response.results} == {"https://x.it/1.pdf", "https://x.it/2.pdf"}


def test_http_segnala_il_rifiuto(config, no_sdk):
    payload = {"model": "claude-opus-5", "stop_reason": "refusal",
               "stop_details": {"explanation": "motivo"}, "content": []}
    with patch("dorklab.providers.http.post_json", return_value=payload):
        with pytest.raises(SearchError):
            ClaudeAgenticProvider().search("test", config=config)


def test_errore_web_search_non_interrompe(config, no_sdk):
    # Un errore dello strumento di ricerca web e' un oggetto, non una lista.
    payload = {"model": "claude-opus-5", "stop_reason": "end_turn",
               "content": [{"type": "web_search_tool_result",
                            "content": {"error_code": "max_uses_exceeded"}}]}
    with patch("dorklab.providers.http.post_json", return_value=payload):
        response = ClaudeAgenticProvider().search("test", config=config)
    assert response.results == []   # nessun risultato, ma nessuna eccezione
