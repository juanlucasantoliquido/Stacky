"""
Tests F0 del Plan 84 — campo restart_required en FlagSpec + snapshot boot + pending_restart.

Escribir PRIMERO antes de implementar el código.
"""

import os
import sys
import pytest
from unittest.mock import patch

# Agregar backend al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services import harness_flags


def test_flagspec_restart_required_default_false():
    """Un FlagSpec mínimo sin el kwarg tiene restart_required is False."""
    spec = harness_flags.FlagSpec(
        key="STACKY_TEST_FLAG",
        type="bool",
        label="Test",
        description="Test flag",
        group="global"
    )
    assert spec.restart_required is False


def test_pending_restart_false_without_snapshot():
    """Con _BOOT_VALUES vacío, pending_restart es False (fail-open)."""
    # Limpiar el snapshot
    harness_flags._BOOT_VALUES.clear()

    spec = harness_flags.FlagSpec(
        key="STACKY_TEST_RESTART",
        type="int",
        label="Test",
        description="Test restart flag",
        group="global",
        restart_required=True
    )

    # Sin snapshot, debe ser False
    assert harness_flags.pending_restart(spec, 5) is False


def test_pending_restart_true_when_value_differs():
    """pending_restart es True cuando el valor actual difiere del snapshot."""
    spec = harness_flags.FlagSpec(
        key="STACKY_TEST_RESTART",
        type="int",
        label="Test",
        description="Test restart flag",
        group="global",
        restart_required=True
    )

    # Sembrar snapshot con valor 0
    harness_flags._BOOT_VALUES["STACKY_TEST_RESTART"] = 0

    # Valor diferente = True
    assert harness_flags.pending_restart(spec, 6) is True

    # Valor igual = False
    assert harness_flags.pending_restart(spec, 0) is False


def test_pending_restart_false_for_normal_flag():
    """Una flag con restart_required=False devuelve False aunque haya snapshot."""
    spec = harness_flags.FlagSpec(
        key="STACKY_TEST_NORMAL",
        type="int",
        label="Test",
        description="Test normal flag",
        group="global",
        restart_required=False
    )

    # Sembrar snapshot
    harness_flags._BOOT_VALUES["STACKY_TEST_NORMAL"] = 0

    # Aunque hay snapshot y valor distinto, debe ser False
    assert harness_flags.pending_restart(spec, 5) is False


def test_snapshot_boot_values_captures_only_restart_required():
    """snapshot_boot_values solo captura flags con restart_required=True."""
    # Crear dos specs sintéticos
    spec_a = harness_flags.FlagSpec(
        key="STACKY_TEST_A",
        type="int",
        label="A",
        description="Flag A con restart_required",
        group="global",
        env_only=True,
        restart_required=True
    )
    spec_b = harness_flags.FlagSpec(
        key="STACKY_TEST_B",
        type="int",
        label="B",
        description="Flag B sin restart_required",
        group="global",
        env_only=True
    )

    # Parchear FLAG_REGISTRY temporalmente
    with patch.object(harness_flags, "FLAG_REGISTRY", (spec_a, spec_b)):
        # Limpiar snapshot anterior
        harness_flags._BOOT_VALUES.clear()

        # Ejecutar snapshot
        harness_flags.snapshot_boot_values()

        # Solo debe estar la key A
        assert set(harness_flags._BOOT_VALUES.keys()) == {"STACKY_TEST_A"}


def test_read_current_serializes_restart_fields():
    """Todo item del GET tiene restart_required, pending_restart y boot_value."""
    # Limpiar snapshot
    harness_flags._BOOT_VALUES.clear()

    # Usar un spec REAL del registry (no sintético, para evitar AttributeError)
    # STACKY_MAX_CONCURRENT_RUNS es una flag normal (no restart_required)
    spec = None
    for s in harness_flags.FLAG_REGISTRY:
        if s.key == "STACKY_MAX_CONCURRENT_RUNS":
            spec = s
            break

    assert spec is not None, "STACKY_MAX_CONCURRENT_RUNS debe estar en FLAG_REGISTRY"

    items = harness_flags.read_current()
    item = next(i for i in items if i["key"] == "STACKY_MAX_CONCURRENT_RUNS")

    # Campos deben estar presentes
    assert "restart_required" in item
    assert isinstance(item["restart_required"], bool)

    assert "pending_restart" in item
    assert isinstance(item["pending_restart"], bool)

    assert "boot_value" in item
    # boot_value es None cuando no hay pendiente
    assert item["boot_value"] is None


def test_read_current_pending_restart_reflects_env_change():
    """Para una flag env_only con restart_required: pending_restart refleja cambio de env."""
    # Crear un spec sintético env_only con restart_required=True
    spec = harness_flags.FlagSpec(
        key="STACKY_TEST_ENV_RESTART",
        type="int",
        label="Test",
        description="Test env_only restart flag",
        group="global",
        env_only=True,
        restart_required=True
    )

    # Limpiar snapshot
    harness_flags._BOOT_VALUES.clear()

    # Simular snapshot sin env seteada (boot = 0)
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("STACKY_TEST_ENV_RESTART", None)
        harness_flags._BOOT_VALUES["STACKY_TEST_ENV_RESTART"] = harness_flags._current_value(spec)

    # Ahora setear la env var
    with patch.dict(os.environ, {"STACKY_TEST_ENV_RESTART": "12"}):
        # Parchear el registry temporalmente
        with patch.object(harness_flags, "FLAG_REGISTRY", (spec,)):
            items = harness_flags.read_current()

            assert len(items) == 1
            item = items[0]

            # Debe tener pending_restart True
            assert item["pending_restart"] is True
            # boot_value debe ser el valor del snapshot (0)
            assert item["boot_value"] == 0


def test_read_current_str_env_only_unset_is_empty_string():
    """Para una flag type='str' env_only sin configurar, value == '' (no 0)."""
    # Buscar una flag str env_only (STACKY_PROJECTS_BOM_PATTERN, por ejemplo)
    spec = None
    for s in harness_flags.FLAG_REGISTRY:
        if s.type == "str" and s.env_only:
            spec = s
            break

    if spec is None:
        pytest.skip("No hay flag str env_only en el registry")

    # Limpiar snapshot
    harness_flags._BOOT_VALUES.clear()

    # Asegurar que la env var NO esté seteada
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop(spec.key, None)

        items = harness_flags.read_current()
        item = next(i for i in items if i["key"] == spec.key)

        # El valor debe ser string vacío, no 0
        assert item["value"] == ""
        assert isinstance(item["value"], str)


# Receta de auditoría (determinista) para decidir si una flag es restart_required:
# grep -o 'STACKY_[A-Z_]*' backend/app.py | sort -u  → cruzar contra FLAG_REGISTRY.
# Toda key del registry consumida dentro de create_app() (gate o intervalo de un
# daemon) es restart_required. Cualquier otra key NO lo es (se lee call-time).
# Auditoría 2026-07-02: watchers/reaper/recovery/manifest de app.py NO están en el
# registry (kill-switches internos env-only) → no aplican.
_EXPECTED_RESTART_REQUIRED = frozenset({
    "STACKY_DIGEST_INTERVAL_HOURS",
    "STACKY_MEMORY_REVIEW_SWEEP_HOURS",
    "STACKY_ADO_EDIT_LEARNING_ENABLED",
    "STACKY_ADO_EDIT_SWEEP_HOURS",
    "STACKY_EVALS_INTERVAL_HOURS",
})


def test_restart_required_map_is_frozen():
    actual = {s.key for s in harness_flags.FLAG_REGISTRY if s.restart_required}
    assert actual == _EXPECTED_RESTART_REQUIRED


def test_app_startup_flag_reads_are_all_declared():
    """Todo token STACKY_* de app.py que sea key del registry debe estar declarado."""
    import re
    from pathlib import Path
    src = (Path(__file__).parent.parent / "app.py").read_text(encoding="utf-8")
    tokens_in_app = set(re.findall(r"STACKY_[A-Z_]+", src))
    registry_keys = {s.key for s in harness_flags.FLAG_REGISTRY}
    startup_reads = tokens_in_app & registry_keys
    assert startup_reads <= _EXPECTED_RESTART_REQUIRED, (
        f"Keys del registry mencionadas en app.py sin declarar restart_required: "
        f"{sorted(startup_reads - _EXPECTED_RESTART_REQUIRED)}"
    )
    # Escape hatch: si app.py necesita leer una key en CALL-TIME, mover a servicio
    # o si es boot-time, declararla restart_required=True y agregar al mapa congelado.


def test_create_app_populates_boot_snapshot():
    """Centinela de wiring: create_app() llena _BOOT_VALUES."""
    import sys
    from io import StringIO
    from pathlib import Path

    # Importar app.py para ejecutar create_app()
    # Necesitamos capturar el output para evitar logs
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    try:
        # Importar y crear la app
        app_module = __import__("app", fromlist=["create_app"])
        app = app_module.create_app()

        # Verificar que el snapshot está poblado
        assert set(harness_flags._BOOT_VALUES.keys()) == _EXPECTED_RESTART_REQUIRED
    finally:
        sys.stdout = old_stdout
