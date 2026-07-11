"""Plan 75 F6 — Tests de wiring del flag STACKY_GITLAB_DEEP_LINKS_ENABLED.

Verifica (C2):
  1. Flag OFF -> item_url, mr_url, commit_url, epic_url devuelven None.
  2. Flag ON -> item_url devuelve URL compuesta con %2F (no None).
  3. harness_defaults.env contiene STACKY_GITLAB_DEEP_LINKS_ENABLED=false.
  4. config.py tiene STACKY_GITLAB_DEEP_LINKS_ENABLED default False.
  5. Los archivos test_plan75_*.py estan registrados en el ratchet run_harness_tests.sh.
"""
import os
from pathlib import Path
from unittest.mock import MagicMock
import config as config_module


def _make_provider():
    """GitLabTrackerProvider con client mockeado."""
    from services.gitlab_provider import GitLabTrackerProvider
    provider = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    mock_client = MagicMock()
    mock_client._base_url = "https://gl.example.com"
    mock_client._project_path.return_value = "rs%2Fpacifico%2Fstrat"
    provider._client = mock_client
    provider._project = "rs/pacifico/strat"
    provider._group = "my-group"
    provider._epics_native = True
    return provider


def test_f6_1_flag_off_all_methods_return_none(monkeypatch):
    """Gate C2: flag OFF -> los 4 metodos devuelven None."""
    monkeypatch.setattr(config_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", False)
    provider = _make_provider()
    assert provider.item_url("1") is None
    assert provider.mr_url("1") is None
    assert provider.commit_url("abc") is None
    assert provider.epic_url("1") is None


def test_f6_2_flag_on_item_url_returns_composed_url(monkeypatch):
    """Flag ON -> item_url devuelve URL con %2F (encoding correcto)."""
    monkeypatch.setattr(config_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", True)
    provider = _make_provider()
    result = provider.item_url("42")
    assert result is not None
    assert "%2F" in result
    assert "%25" not in result


def test_f6_3_harness_defaults_contains_flag():
    """harness_defaults.env tiene STACKY_GITLAB_DEEP_LINKS_ENABLED=false."""
    backend_root = Path(__file__).parent.parent
    defaults_path = backend_root / "harness_defaults.env"
    assert defaults_path.exists(), f"harness_defaults.env no encontrado en {defaults_path}"
    content = defaults_path.read_text(encoding="utf-8")
    assert "STACKY_GITLAB_DEEP_LINKS_ENABLED=false" in content, (
        "harness_defaults.env debe tener STACKY_GITLAB_DEEP_LINKS_ENABLED=false"
    )


def test_f6_4_config_default_is_true():
    """config.py: STACKY_GITLAB_DEEP_LINKS_ENABLED default True sin env var.

    Activación operador 2026-07-10: promovida a capacidad opt-in default ON.
    """
    orig = os.environ.pop("STACKY_GITLAB_DEEP_LINKS_ENABLED", None)
    try:
        import importlib
        import config as cfg_mod
        importlib.reload(cfg_mod)
        assert cfg_mod.config.STACKY_GITLAB_DEEP_LINKS_ENABLED is True
    finally:
        if orig is not None:
            os.environ["STACKY_GITLAB_DEEP_LINKS_ENABLED"] = orig
        import importlib
        import config as cfg_mod2
        importlib.reload(cfg_mod2)


def test_f6_5_ratchet_includes_plan75_files():
    """Los 6 archivos test_plan75_*.py estan registrados en run_harness_tests.sh."""
    backend_root = Path(__file__).parent.parent
    ratchet_path = backend_root / "scripts" / "run_harness_tests.sh"
    assert ratchet_path.exists(), f"run_harness_tests.sh no encontrado en {ratchet_path}"
    content = ratchet_path.read_text(encoding="utf-8")
    expected = [
        "test_plan75_deep_links_compose.py",
        "test_plan75_gitlab_provider_urls.py",
        "test_plan75_deep_links_epic_fallback.py",
        "test_plan75_deep_links_bidirectional.py",
        "test_plan75_deep_links_wiring.py",
        "test_plan75_deep_links_no_double_encode.py",
    ]
    missing = [f for f in expected if f not in content]
    assert not missing, f"Archivos no registrados en ratchet: {missing}"
