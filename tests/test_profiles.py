"""Test dei profili di rete (standard / discreto / occulto)."""

from dorklab.config import BROWSER_USER_AGENT, Config, NETWORK_PROFILES


def test_profili_disponibili():
    assert set(NETWORK_PROFILES) == {"standard", "discreto", "occulto"}


def test_applica_profilo_occulto():
    c = Config()
    c.apply_profile("occulto")
    assert c.get("network_profile") == "occulto"
    assert c.get("request_delay") == 9.0
    assert c.get("request_jitter") == 0.6
    assert c.get("browser_ua") is True
    assert c.archive_only() is True


def test_user_agent_da_browser_solo_in_occulto():
    c = Config()
    assert c.effective_user_agent().startswith("DorkLab")
    c.apply_profile("occulto")
    assert c.effective_user_agent() == BROWSER_USER_AGENT
    c.apply_profile("standard")
    assert c.effective_user_agent().startswith("DorkLab")


def test_standard_non_e_archive_only():
    c = Config()
    c.apply_profile("standard")
    assert c.archive_only() is False


def test_jitter_entro_i_limiti():
    c = Config()
    c.apply_profile("occulto")   # base 9.0, jitter 0.6 -> [3.6, 14.4]
    for _ in range(50):
        d = c.jittered_delay()
        assert 3.6 - 0.01 <= d <= 14.4 + 0.01


def test_jitter_zero_restituisce_il_ritardo_base():
    c = Config()
    c.set("request_delay", 2.0)
    c.set("request_jitter", 0.0)
    assert c.jittered_delay() == 2.0


def test_profilo_ignoto_non_cambia_nulla():
    c = Config()
    prima = c.get("request_delay")
    c.apply_profile("inesistente")
    assert c.get("request_delay") == prima
