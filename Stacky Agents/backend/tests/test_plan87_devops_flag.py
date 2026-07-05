"""tests/test_plan87_devops_flag.py — F0 tests (flag master STACKY_DEVOPS_PANEL_ENABLED)."""
import pytest
import importlib


@pytest.fixture(autouse=True)
def reload_harness_flags():
    """Recargar harness_flags para evitar cache de pytest."""
    import sys
    # Eliminar del cache
    for mod in list(sys.modules.keys()):
        if 'harness_flags' in mod or 'harness_flags_help' in mod:
            del sys.modules[mod]
    # Recargar
    import services.harness_flags as hf
    importlib.reload(hf)
    import services.harness_flags_help as hfh
    importlib.reload(hfh)
    yield


class TestF0FlagInRegistry:
    """STACKY_DEVOPS_PANEL_ENABLED está en FLAG_REGISTRY con los campos correctos."""

    def test_f0_flag_in_registry(self):
        """La key existe en FLAG_REGISTRY con env_only=False, requires correcto."""
        from services.harness_flags import FLAG_REGISTRY
        keys = [f.key for f in FLAG_REGISTRY]
        assert "STACKY_DEVOPS_PANEL_ENABLED" in keys
        # Encontrar el spec
        spec = next(f for f in FLAG_REGISTRY if f.key == "STACKY_DEVOPS_PANEL_ENABLED")
        assert spec.env_only is False
        # Supervisión 2026-07-05: el plan 87 F0 declaraba requires=GENERATOR, pero esa
        # arista viola la regla R4 del Plan 82 (profundidad máx 1) al combinarse con las
        # hijas de la serie (88/89/90/91 requieren el PANEL) y contradice el diseño de
        # degradación del propio 87 (FlagGateBanner). La flag master queda SIN requires.
        assert spec.requires is None
        assert spec.group == "global"
        assert spec.label != ""  # label no vacío

    def test_f0_flag_in_category_devops(self):
        """La key está en la categoría devops de _CATEGORY_KEYS."""
        from services.harness_flags import _CATEGORY_KEYS
        assert "devops" in _CATEGORY_KEYS
        assert "STACKY_DEVOPS_PANEL_ENABLED" in _CATEGORY_KEYS["devops"]


class TestF0ConfigDefault:
    """Config default OFF sin importar env del runner (FIX C8 — monkeypatch)."""

    def test_f0_config_default_off(self, monkeypatch):
        """Sin la env var, config.STACKY_DEVOPS_PANEL_ENABLED es False."""
        monkeypatch.delenv("STACKY_DEVOPS_PANEL_ENABLED", raising=False)
        # Recargar config para limpiar cache
        import importlib, config
        importlib.reload(config)
        assert config.config.STACKY_DEVOPS_PANEL_ENABLED is False


class TestF0PlainHelp:
    """La flag tiene entrada PlainHelp en harness_flags_help.py."""

    def test_f0_flag_has_plain_help(self):
        """Existe entrada de ayuda para la key."""
        from services.harness_flags_help import PLAIN_HELP
        assert "STACKY_DEVOPS_PANEL_ENABLED" in PLAIN_HELP
        help_obj = PLAIN_HELP["STACKY_DEVOPS_PANEL_ENABLED"]
        # Verificar que tiene estructura esperada (qué pasa ON/OFF, ejemplo)
        assert len(help_obj.what) > 20  # qué hace, mínimo
        assert len(help_obj.on_effect) > 20  # on_effect mínimo
        assert len(help_obj.off_effect) > 20  # off_effect mínimo
        assert len(help_obj.example) > 20  # ejemplo mínimo


class TestF0HarnessDefaults:
    """C13: harness_defaults.env contiene la línea de la flag."""

    def test_f0_harness_defaults_contains_flag(self):
        """backend/harness_defaults.env existe y contiene STACKY_DEVOPS_PANEL_ENABLED=false."""
        from pathlib import Path
        backend_root = Path(__file__).parent.parent
        env_file = backend_root / "harness_defaults.env"
        assert env_file.exists(), f"{env_file} no existe"
        content = env_file.read_text(encoding="utf-8")
        assert "STACKY_DEVOPS_PANEL_ENABLED=false" in content
